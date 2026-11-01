import json
import subprocess
import sys

import pytest

from askmill.profiles import from_pdf2data, model_revision
from askmill.runner import RunError


def test_cached_model_mutation_changes_identity(tmp_path):
    (tmp_path / "config.json").write_text("{}")
    first = model_revision(tmp_path)
    (tmp_path / "weights.bin").write_bytes(b"changed")
    assert first != model_revision(tmp_path)


def test_old_profile_conversion_preserves_paths(tmp_path):
    old = dict(
        provider="mlx-vlm",
        model="qwen",
        python="/venv/bin/python",
        model_path="/cache/model",
    )
    converted = from_pdf2data(old, "sha256:fixture")
    assert (
        converted.python == old["python"] and converted.model_path == old["model_path"]
    )
    assert old == dict(
        provider="mlx-vlm",
        model="qwen",
        python="/venv/bin/python",
        model_path="/cache/model",
    )
    with pytest.raises(RunError):
        from_pdf2data(dict(provider="ollama"), "unverified")


def test_cli_incomplete_exit_and_receipt(endpoint, tmp_path):
    profile, state = endpoint
    state["complete"] = False
    config = tmp_path / "profiles.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": "askmill.profiles.v1",
                "profiles": {"test": profile.model_dump()},
            }
        )
    )
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Synthetic failing test")
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "askmill.cli",
            "--config",
            str(config),
            "--store",
            str(tmp_path / "r"),
            "--lease",
            str(tmp_path / "lock"),
            "run",
            "--profile",
            "test",
            "--input",
            str(prompt),
        ],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 3, run.stderr
    data = json.loads(run.stdout)
    assert data["status"] == "incomplete"
    assert (tmp_path / "r" / (data["receipt_id"] + ".json")).exists()


def test_mcp_stdio_calls_shared_runner(endpoint, tmp_path):
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    profile, state = endpoint
    config = tmp_path / "profiles.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": "askmill.profiles.v1",
                "profiles": {"test": profile.model_dump()},
            }
        )
    )

    async def check():
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "askmill.cli",
                "--config",
                str(config),
                "--store",
                str(tmp_path / "r"),
                "--lease",
                str(tmp_path / "lock"),
                "mcp",
            ],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                tools = await client.list_tools()
                assert [tool.name for tool in tools.tools] == ["run"]
                result = await client.call_tool(
                    "run", {"profile": "test", "prompt": "Explain this log."}
                )
                assert not result.isError
                assert "candidate" in result.content[0].text

    anyio.run(check)
    assert len(state["calls"]) == 1
