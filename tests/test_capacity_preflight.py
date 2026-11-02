"""Offline utility controls; these are not source/model accuracy cases."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "capacity_preflight", ROOT / "tools/capacity_preflight.py"
)
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


def test_shipped_request_stays_unknown_and_inputs_unchanged():
    config = ROOT / "examples/profile.template.json"
    request = ROOT / "examples/structured-source-id/request.json"
    before = [p.read_bytes() for p in (config, request)]
    report = preflight.preflight(config, "dev-text", request, {"test_control": True})
    assert report["status"] == "capacity_unknown"
    assert report["request"]["schema_gate"] == "passed"
    assert report["tokenization"]["exact_input_tokens"] is None
    assert report["tokenization"]["conservative_upper_bound"] is None
    assert report["capacity"]["state"] == "unknown"
    assert report["capacity"]["input_budget_if_profile_context_is_honored"] is None
    assert report["boundaries"]["execution_authorized"] is False
    assert before == [p.read_bytes() for p in (config, request)]


@pytest.mark.parametrize("field", ["sources", "images", "response_schema"])
def test_invalid_envelope_retains_refusal_without_counting_null(field, tmp_path):
    # Mutate an existing software fixture, never a domain/source acceptance case.
    body = json.loads(
        (ROOT / "examples/structured-source-id/request.json").read_bytes()
    )
    body[field] = None
    request = tmp_path / "refusal.json"
    request.write_text(json.dumps(body))
    report = preflight.preflight(
        ROOT / "examples/profile.template.json",
        "dev-text",
        request,
        {"test_control": True},
    )
    assert report["status"] == "request_rejected"
    assert report["request"]["errors"]
    assert report["capacity"]["state"] == "unknown"


def test_oversize_metadata_never_opened(tmp_path, monkeypatch):
    path = tmp_path / "oversize"
    with path.open("wb") as handle:
        handle.truncate(preflight.META_LIMIT + 1)

    def forbidden(*args, **kwargs):
        pytest.fail("Oversize metadata was opened")

    monkeypatch.setattr(preflight, "read_bytes", forbidden)
    with pytest.raises(ValueError, match="not opened"):
        preflight.metadata_bytes(path)


def test_metadata_alias_to_weight_digest_rejected_before_blob_read(tmp_path):
    digest = "sha256:" + "a" * 64
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "config": {"digest": digest, "size": 1},
                "layers": [
                    {
                        "mediaType": "application/vnd.ollama.image.model",
                        "digest": digest,
                        "size": 1,
                    }
                ],
            }
        )
    )
    profile = SimpleNamespace(
        provider="ollama", revision=preflight.sha(manifest.read_bytes())
    )
    with pytest.raises(ValueError, match="weight-container alias"):
        preflight.ollama_metadata(profile, manifest, tmp_path / "no-blobs-exist")


def test_manifest_revision_mismatch_rejected_before_layer_read(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    profile = SimpleNamespace(provider="ollama", revision="b" * 64)
    with pytest.raises(ValueError, match="do not match profile revision"):
        preflight.ollama_metadata(profile, manifest, tmp_path / "no-blobs-exist")


def test_wrong_wheel_hash_refused_before_import_identity_check(tmp_path):
    wheel = tmp_path / "wrong.whl"
    wheel.write_bytes(b"not a qualified wheel")
    with pytest.raises(ValueError, match="checksum mismatch"):
        preflight.qualified_install(wheel, "c" * 64)


def test_pattern_grammar_refusal_preserves_original_schema(tmp_path):
    from askmill.structured import schema_digest

    body = json.loads(
        (ROOT / "examples/structured-source-id/request.json").read_bytes()
    )
    document = body["response_schema"]["document"]
    document["properties"]["source_id"]["pattern"] = "^[A-Za-z0-9_.:-]+$"
    body["response_schema"]["sha256"] = schema_digest(document)
    request = tmp_path / "unsupported-pattern.json"
    request.write_text(json.dumps(body))
    before = request.read_bytes()
    report = preflight.preflight(
        ROOT / "examples/profile.template.json",
        "dev-text",
        request,
        {"test_control": True},
    )
    assert report["status"] == "request_rejected"
    assert any("pattern" in item["message"] for item in report["request"]["errors"])
    assert report["tokenization"]["exact_input_tokens"] is None
    assert request.read_bytes() == before


def test_smaller_prompt_with_declared_budget_cannot_satisfy_missing_tokenizer(tmp_path):
    registry = json.loads((ROOT / "examples/profile.template.json").read_bytes())
    registry["profiles"]["dev-text"].update(
        {
            "schema_version": "askmill.profile.v2",
            "generation": {"context_tokens": 8192, "thinking": False},
        }
    )
    config = tmp_path / "profile.json"
    config.write_text(json.dumps(registry))
    body = json.loads(
        (ROOT / "examples/structured-source-id/request.json").read_bytes()
    )
    body["max_tokens"] = 2048
    prompt = body["prompt"]
    reports = []
    for index, text in enumerate((prompt, prompt[: len(prompt) // 2])):
        body["prompt"] = text
        request = tmp_path / (str(index) + ".json")
        request.write_text(json.dumps(body))
        reports.append(
            preflight.preflight(config, "dev-text", request, {"test_control": True})
        )
    assert (
        reports[1]["request"]["prompt_utf8_bytes"]
        < reports[0]["request"]["prompt_utf8_bytes"]
    )
    for report in reports:
        assert report["request"]["schema_gate"] == "passed"
        assert report["capacity"]["input_budget_if_profile_context_is_honored"] == 6144
        assert report["capacity"]["state"] == "unknown"
        assert report["tokenization"]["conservative_upper_bound"] is None
        assert (
            report["tokenization"]["missing_dependencies"]["revision_bound_tokenizer"][
                "state"
            ]
            == "unqualified"
        )
        assert report["boundaries"]["execution_authorized"] is False
