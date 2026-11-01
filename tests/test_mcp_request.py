"""Actual stdio admission checks; private real requests never enter the repo."""

import copy
import hashlib
import json
import os
from pathlib import Path
import sys

import anyio
import pytest

from askmill import __version__
from askmill.mcp import create_server


def test_mcp_discovery_has_closed_full_request_schema(tmp_path):
    async def check():
        server = create_server(
            tmp_path / "unconfigured.json", tmp_path / "receipts", [tmp_path / "lease"]
        )
        tools = {tool.name: tool for tool in await server.list_tools()}
        assert set(tools) == {"run", "run_batch", "run_request_v1"}
        assert all(
            t.inputSchema["additionalProperties"] is False for t in tools.values()
        )
        schema = tools["run_request_v1"].inputSchema
        assert schema["$id"] == "urn:askmill:mcp-run-request:v1"
        assert schema["$defs"]["Request"]["properties"]["sources"]["maxItems"] == 128
        assert schema["$defs"]["Source"]["additionalProperties"] is False
        assert set(schema["required"]) == {"profile", "request"}
        assert (
            server._mcp_server.create_initialization_options().server_version
            == __version__
        )

    anyio.run(check)


def test_mcp_unknown_arguments_rejected_before_profile_or_session(tmp_path):
    async def check():
        server = create_server(
            tmp_path / "unconfigured.json", tmp_path / "receipts", [tmp_path / "lease"]
        )
        for name in ["run", "run_batch", "run_request_v1"]:
            with pytest.raises(ValueError, match="Invalid MCP arguments"):
                await server.call_tool(name, {"unrecognized_argument": __version__})
        assert not (tmp_path / "receipts").exists()

    anyio.run(check)


def probe_real_stdio(request_path, output):
    """Roundtrip an actual request to a rejecting Session guard, never a model."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    raw = request_path.read_bytes()
    actual = json.loads(raw)
    output.mkdir(parents=True, exist_ok=False)
    captured = output / "guard.jsonl"
    bootstrap = """
import json,os
from pathlib import Path
import askmill.mcp as m
import askmill.runner as r
class NoInference:
    def __init__(self,profile,store,lease):
        self.profile=profile
        with Path(os.environ['ASKMILL_GUARD']).open('a')as f:f.write(json.dumps({'event':'session_constructed'})+'\\n')
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def run(self,request):
        with Path(os.environ['ASKMILL_GUARD']).open('a')as f:f.write(json.dumps({'event':'request_admitted','request':request.model_dump()})+'\\n')
        raise RuntimeError('ADMISSION_ONLY_NO_INFERENCE')
m.Session=NoInference
r.Session=NoInference
from askmill.cli import main
import sys
sys.exit(main())
"""
    args = ["-I", "-c", bootstrap, "--store", str(output / "receipts"), "mcp"]
    schema_checks = []

    def events():
        return (
            [json.loads(line) for line in captured.read_text().splitlines()]
            if captured.exists()
            else []
        )

    async def check():
        params = StdioServerParameters(
            command=sys.executable,
            args=args,
            env={**os.environ, "ASKMILL_GUARD": str(captured)},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                initialized = await client.initialize()
                assert initialized.serverInfo.version == __version__
                tools = await client.list_tools()
                identity = await client.read_resource("askmill://producer")
                producer = json.loads(identity.contents[0].text)
                assert producer["application_version"] == __version__
                assert producer["mcp_sdk_version"] != __version__
                assert producer["full_request_tool"] == "run_request_v1"
                (output / "initialize.json").write_text(
                    initialized.model_dump_json(indent=2)
                )
                (output / "tool-schemas.json").write_text(
                    tools.model_dump_json(indent=2)
                )
                (output / "producer.json").write_text(
                    json.dumps(producer, indent=2) + "\n"
                )
                for name, arguments in [
                    ("run_request_v1", {"profile": "general", "request": actual}),
                    (
                        "run_batch",
                        {
                            "profile": "general",
                            "schema_version": "askmill.batch.v2",
                            "requests": [actual],
                        },
                    ),
                ]:
                    result = await client.call_tool(name, arguments)
                    assert (
                        result.isError
                        and "ADMISSION_ONLY_NO_INFERENCE" in result.content[0].text
                    )
                    assert events()[-1]["request"] == actual
                positive_events = len(events())
                mutations = []
                invalid = copy.deepcopy(actual)
                invalid["max_tokens"] = -1
                mutations.append(
                    ("invalid-token-bound", {"profile": "general", "request": invalid})
                )
                duplicated = copy.deepcopy(actual)
                duplicated["sources"] *= 2
                mutations.append(
                    (
                        "duplicate-source-id",
                        {"profile": "general", "request": duplicated},
                    )
                )
                unknown = copy.deepcopy(actual)
                unknown["unrecognized_field"] = actual["schema_version"]
                mutations.append(
                    (
                        "unknown-request-field",
                        {"profile": "general", "request": unknown},
                    )
                )
                mutations.append(
                    (
                        "unknown-tool-argument",
                        {
                            "profile": "general",
                            "request": actual,
                            "unrecognized": actual["schema_version"],
                        },
                    )
                )
                count = copy.deepcopy(actual)
                source = count["sources"][0]
                count["sources"] = [
                    {**source, "id": source["id"] + ":" + str(i)} for i in range(129)
                ]
                mutations.append(
                    ("source-cardinality", {"profile": "general", "request": count})
                )
                metadata = copy.deepcopy(count)
                metadata["sources"] = metadata["sources"][:128]
                for source in metadata["sources"]:
                    source["reference"] = (source["reference"] * 4096)[:4096]
                mutations.append(
                    (
                        "source-metadata-byte-bound",
                        {"profile": "general", "request": metadata},
                    )
                )
                oversized = copy.deepcopy(actual)
                reference = actual["sources"][0]["reference"]
                oversized["images"] = [
                    (reference * ((4194305 + len(reference) - 1) // len(reference)))[
                        :4194305
                    ]
                ]
                mutations.append(
                    ("request-byte-bound", {"profile": "general", "request": oversized})
                )
                for name, arguments in mutations:
                    result = await client.call_tool("run_request_v1", arguments)
                    assert (
                        result.isError
                        and "ADMISSION_ONLY_NO_INFERENCE" not in result.content[0].text
                    )
                    assert len(events()) == positive_events
                    (output / (name + ".json")).write_text(
                        result.model_dump_json(indent=2)
                    )
                    schema_checks.append(
                        {"case": name, "rejected_before_session": True}
                    )
                # Existing flat run does not silently accept/drop sources or other extras.
                result = await client.call_tool(
                    "run",
                    {
                        "profile": "general",
                        "prompt": actual["prompt"],
                        "sources": actual["sources"],
                    },
                )
                assert result.isError and len(events()) == positive_events
                schema_checks.append(
                    {
                        "case": "legacy-run-unknown-sources",
                        "rejected_before_session": True,
                    }
                )
        assert request_path.read_bytes() == raw
        assert not (output / "receipts").exists()
        report = {
            "askmill_version": __version__,
            "source_request_sha256": hashlib.sha256(raw).hexdigest(),
            "full_request_metadata_admitted_unchanged": True,
            "batch_metadata_admitted_unchanged": True,
            "refusal_controls": schema_checks,
            "source_request_unchanged": True,
            "guarded_admissions": 2,
            "new_model_calls": 0,
            "new_accuracy_cases": 0,
            "positive_source_bound_generation": "not_tested",
            "real_result_receipt_acceptance": "not_tested",
        }
        (output / "receipt.json").write_text(json.dumps(report, indent=2) + "\n")
        return report

    return anyio.run(check)


def test_real_request_stdio_admission_and_refusal_controls(tmp_path):
    name = os.environ.get("ASKMILL_REAL_REQUEST")
    if not name:
        pytest.skip("Supply an authorized actual request outside the public repository")
    report = probe_real_stdio(Path(name), tmp_path / "actual-stdio-admission")
    assert len(report["refusal_controls"]) == 8
