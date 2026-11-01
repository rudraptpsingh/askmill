import copy
import json
import subprocess
import sys

import pytest
from pydantic import ValidationError

from askmill import Batch, Request, ResponseSchema
from askmill.runner import RunError, Session, digest, run_batch
from askmill.structured import DIALECT, check_schema, schema_digest


def document():
    # Synthetic source IDs and roles; consumer cross-field semantics stay external.
    return {
        "$schema": DIALECT,
        "type": "object",
        "properties": {
            "role": {"type": "string", "enum": ["condition", "exception"]},
            "source_ids": {
                "type": "array",
                "items": {"type": "string", "enum": ["a", "b"]},
                "minItems": 1,
                "maxItems": 2,
                "uniqueItems": True,
            },
            "unresolved": {"type": "array", "items": False, "maxItems": 0},
        },
        "required": ["role", "source_ids", "unresolved"],
        "additionalProperties": False,
    }


ANSWER = '{"role":"condition","source_ids":["a"],"unresolved":[]}'


def request(schema=None, **kwargs):
    return Request(
        schema_version="askmill.request.v2",
        prompt="Select source IDs. Return JSON.",
        response_schema=ResponseSchema.from_schema(schema or document()),
        **kwargs,
    )


def configured(endpoint):
    profile, state = endpoint
    state.update(runtime="0.40.13", answer=ANSWER)
    return profile, state


def test_v2_wire_schema_receipt_replay_and_source_boundary(endpoint, tmp_path):
    profile, state = configured(endpoint)
    task = request()
    with Session(profile, tmp_path / "r", tmp_path / "l") as session:
        first = session.run(task)
        replay = session.run(task)
    assert (
        first.status == "completed"
        and first.complete
        and first.response_validation.valid
    )
    assert first.domain_acceptance == "unverified"
    assert replay.replayed and replay.receipt_id == first.receipt_id
    assert len(state["calls"]) == 1
    assert state["calls"][0][1]["format"] == task.response_schema.document
    receipt = json.loads((tmp_path / "r" / (first.receipt_id + ".json")).read_text())[
        "content"
    ]
    assert receipt["schema_version"] == "askmill.receipt.v2"
    assert receipt["request"]["response_schema"]["sha256"] == schema_digest(document())
    assert receipt["raw_response"]["message"]["content"] == ANSWER
    assert receipt["runtime"]["jsonschema"] and receipt["runtime"]["structured_sha256"]
    assert not (tmp_path / "l.unsettled").exists()


def test_schema_changes_separate_cache_and_unstructured_wire(endpoint, tmp_path):
    profile, state = configured(endpoint)
    first_schema = document()
    second_schema = document()
    second_schema["properties"]["role"]["enum"] = ["exception"]
    with Session(profile, tmp_path / "r", tmp_path / "l") as session:
        first = session.run(request(first_schema))
        second = session.run(request(second_schema))
        plain = session.run(Request(prompt=first.text))
    assert len({first.receipt_id, second.receipt_id, plain.receipt_id}) == 3
    assert second.status == "schema_invalid" and second.complete
    assert "format" not in state["calls"][2][1]
    assert "response_schema" not in Request(prompt="old").model_dump()
    assert "response_validation" not in plain.model_dump()
    assert plain.schema_version == "askmill.result.v1"


@pytest.mark.parametrize(
    "answer",
    [
        "```json\n" + ANSWER + "\n```",
        '{"role":"condition",',
        '{"role":"condition","role":"exception","source_ids":["a"],"unresolved":[]}',
        '{"role":"condition","source_ids":["a","a"],"unresolved":[]}',
        '{"role":"condition","source_ids":["unknown"],"unresolved":[]}',
        '{"role":"condition","source_ids":["a"],"unresolved":[],"extra":true}',
        '{"role":NaN,"source_ids":["a"],"unresolved":[]}',
        "",
    ],
)
def test_failed_output_is_retained_without_repair_or_quarantine(
    endpoint, tmp_path, answer
):
    profile, state = configured(endpoint)
    state["answer"] = answer
    with Session(profile, tmp_path / "r", tmp_path / "l") as session:
        result = session.run(request())
        replay = session.run(request())
    assert result.status == "schema_invalid" and result.complete
    assert not result.response_validation.valid and result.response_validation.errors
    assert result.text == answer and replay.replayed
    content = json.loads((tmp_path / "r" / (result.receipt_id + ".json")).read_text())[
        "content"
    ]
    assert content["raw_response"]["message"]["content"] == answer
    assert content["result"]["text"] == answer
    assert not (tmp_path / "l.unsettled").exists()


@pytest.mark.parametrize("answer,valid", [(ANSWER, True), ('{"role":', False)])
def test_completion_and_schema_validity_are_independent(
    endpoint, tmp_path, answer, valid
):
    profile, state = configured(endpoint)
    state.update(answer=answer, complete=False)
    with Session(profile, tmp_path / "r", tmp_path / "l") as session:
        result = session.run(request())
    assert result.status == "incomplete" and not result.complete
    assert result.response_validation.valid is valid
    assert result.domain_acceptance == "unverified" and result.text == answer


def test_capability_rejection_before_reading_or_sending_input(
    mlx_profile, endpoint, tmp_path
):
    profile, state = configured(endpoint)
    # A missing image proves the provider/version check precedes freezing input.
    task = request(images=[str(tmp_path / "missing.png")])
    with Session(mlx_profile, tmp_path / "r", tmp_path / "l") as session:
        with pytest.raises(RunError) as error:
            session.run(task)
        assert error.value.status == "unsupported"
    assert not (tmp_path / "loads").exists()
    for version in ["0.4.9", "unrecognized", "0.40.13-dev"]:
        state["runtime"] = version
        with Session(profile, tmp_path / "r", tmp_path / "l") as session:
            with pytest.raises(RunError) as error:
                session.run(task)
            assert error.value.status == "unsupported"
    assert not state["calls"]


def test_explicit_version_pin_and_mutated_schema_rejected(endpoint, tmp_path):
    schema = ResponseSchema.from_schema(document())
    with pytest.raises(ValidationError):
        Request(prompt="old", response_schema=schema)
    with pytest.raises(ValidationError):
        Request(schema_version="askmill.request.v2", prompt="missing")
    with pytest.raises(ValidationError):
        ResponseSchema(document=document(), sha256="0" * 64)
    with pytest.raises(ValidationError):
        Batch(requests=[request()])
    profile, state = configured(endpoint)
    task = request()
    task.response_schema.document["description"] = "mutated after construction"
    with Session(profile, tmp_path / "r", tmp_path / "l") as session:
        with pytest.raises(ValidationError):
            session.run(task)
    assert not state["calls"]


@pytest.mark.parametrize(
    "schema",
    [
        {"$ref": "https://example.invalid/must-never-be-fetched"},
        {"$ref": "#/$defs/Loop", "$defs": {"Loop": {"$ref": "#/$defs/Loop"}}},
        {"type": "string", "pattern": "(a+)+$"},
        {"type": "string", "format": "email"},
        {"$schema": "https://json-schema.org/draft-07/schema", "type": "object"},
        {"type": "unknown"},
        {"type": "object", "properties": {"a": {"unevaluatedProperties": False}}},
        {"type": "object", "description": "x" * (128 * 1024)},
    ],
)
def test_unsupported_or_invalid_schema_fails_closed(schema):
    with pytest.raises(ValueError):
        ResponseSchema.from_schema(schema)


def test_schema_property_names_are_not_keywords_and_canonical_pin():
    schema = {
        "type": "object",
        "properties": {"$ref": {"type": "string"}},
        "additionalProperties": False,
    }
    check_schema(schema)
    assert schema_digest(schema) == schema_digest(dict(reversed(list(schema.items()))))


def test_cached_validation_is_rechecked_even_with_recomputed_checksum(
    endpoint, tmp_path
):
    profile, state = configured(endpoint)
    task = request()
    with Session(profile, tmp_path / "r", tmp_path / "l") as session:
        result = session.run(task)
        path = tmp_path / "r" / (result.receipt_id + ".json")
        record = json.loads(path.read_text())
        record["content"]["result"]["text"] = "{}"
        record["sha256"] = digest(record["content"])
        path.write_text(json.dumps(record))
        with pytest.raises(RunError, match="Cached response validation"):
            session.run(task)
    assert len(state["calls"]) == 1


def test_batch_schema_failure_not_reported_as_completed(endpoint, tmp_path):
    profile, state = configured(endpoint)
    schema = copy.deepcopy(document())
    schema["properties"]["role"]["const"] = "exception"
    batch = Batch(
        schema_version="askmill.batch.v2", requests=[request(), request(schema)]
    )
    result = run_batch(profile, batch, tmp_path / "r", tmp_path / "l")
    assert result["schema_version"] == "askmill.batch-result.v2"
    assert result["status"] == "schema_invalid"
    assert [r["status"] for r in result["results"]] == ["completed", "schema_invalid"]


def test_cli_json_request_v2_exit_codes(endpoint, tmp_path):
    profile, state = configured(endpoint)
    config = tmp_path / "profiles.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": "askmill.profiles.v1",
                "profiles": {"test": profile.model_dump()},
            }
        )
    )
    task = tmp_path / "request.json"
    task.write_text(request().model_dump_json())
    for answer, complete, expected in [
        (ANSWER, True, 0),
        ("{}", True, 4),
        (ANSWER, False, 3),
    ]:
        state.update(answer=answer, complete=complete)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "askmill.cli",
                "--config",
                str(config),
                "--store",
                str(tmp_path / str(expected)),
                "--lease",
                str(tmp_path / "l"),
                "run",
                "--profile",
                "test",
                "--request",
                str(task),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == expected, result.stdout + result.stderr
        assert json.loads(result.stdout)["domain_acceptance"] == "unverified"


def test_structured_mcp_stdio_uses_same_contract(endpoint, tmp_path):
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    profile, state = configured(endpoint)
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
                str(tmp_path / "l"),
                "mcp",
            ],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                first = await client.call_tool(
                    "run",
                    {
                        "profile": "test",
                        "prompt": "JSON please",
                        "response_schema": request().response_schema.model_dump(),
                    },
                )
                assert not first.isError
                value = json.loads(first.content[0].text)
                assert value["schema_version"] == "askmill.result.v2"
                assert (
                    value["response_validation"]["valid"]
                    and value["domain_acceptance"] == "unverified"
                )
                batch = await client.call_tool(
                    "run_batch",
                    {
                        "profile": "test",
                        "schema_version": "askmill.batch.v2",
                        "requests": [request().model_dump()],
                    },
                )
                assert not batch.isError
                assert json.loads(batch.content[0].text)["status"] == "completed"

    anyio.run(check)
    assert len(state["calls"]) == 2
    assert all(call[1]["format"] == document() for call in state["calls"])


def test_output_and_schema_tree_budgets_fail_closed():
    from askmill.structured import validate_output

    schema = {"type": "string"}
    assert not validate_output('"' + "x" * (1024 * 1024) + '"', schema)["valid"]
    assert not validate_output("[" * 70 + "0" + "]" * 70, {"type": "array"})["valid"]
    assert not validate_output('{"n":1e999}', {"type": "object"})["valid"]
    for _ in range(40):
        schema = {"type": "array", "items": schema}
    with pytest.raises(ValueError, match="budget"):
        ResponseSchema.from_schema(schema)


def test_vision_only_metadata_does_not_bypass_completion_requirement(
    endpoint, tmp_path
):
    profile, state = configured(endpoint)
    profile = profile.model_copy(update={"capabilities": ["vision"]})
    state["capabilities"] = ["vision"]
    with Session(profile, tmp_path / "r", tmp_path / "l") as session:
        with pytest.raises(RunError, match="completion model"):
            session.run(request(images=[str(tmp_path / "missing.png")]))
    assert not state["calls"]


def test_exported_v2_schema_files_validate_actual_result_and_reject_v1(
    endpoint, tmp_path
):
    from pathlib import Path
    import askmill
    from jsonschema import Draft202012Validator

    if "site-packages" in Path(askmill.__file__).parts:
        schemas = Path(sys.prefix) / "share/askmill/schemas"
    else:
        schemas = Path(__file__).resolve().parents[1] / "schemas"
    profile, _ = configured(endpoint)
    task = request()
    with Session(profile, tmp_path / "r", tmp_path / "l") as session:
        result = session.run(task)
    for name, value in [
        ("request-v2", task.model_dump()),
        ("result-v2", result.model_dump()),
        (
            "batch-v2",
            Batch(schema_version="askmill.batch.v2", requests=[task]).model_dump(),
        ),
        ("response-schema-v1", task.response_schema.model_dump()),
    ]:
        schema = json.loads((schemas / (name + ".json")).read_text())
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(value)
        if name != "response-schema-v1":
            assert not Draft202012Validator(schema).is_valid(
                {**value, "schema_version": "askmill.request.v1"}
            )
