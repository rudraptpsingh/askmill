"""Offline boundary controls; actual retained data stays outside the repository."""

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

from askmill.jsonio import load
from askmill.runner import digest

spec = importlib.util.spec_from_file_location(
    "report_receipt_gate",
    Path(__file__).resolve().parents[1] / "tools/report_receipt_gate.py",
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


@pytest.fixture
def files(tmp_path):
    name = os.environ.get("ASKMILL_REAL_RECEIPT")
    if not name:
        pytest.skip("Supply a private authorized structured receipt")
    path = Path(name)
    record = load(path, 96 * 1024 * 1024)
    content = record["content"]
    settlement = load(
        path.parent / "settlements" / (content["result"]["session_id"] + ".json")
    )
    objects = {
        "receipt": record,
        "settlement": settlement,
        "request": content["request"],
        "profile": content["profile"],
        "runtime": content["runtime"],
        "stdout_result": content["result"],
    }
    manifest = {
        "schema_version": "askmill.report-receipt-gate.v1",
        "lease_handles_closed": 2,
    }

    def write(name, obj):
        raw = json.dumps(obj).encode()
        target = tmp_path / (name + ".json")
        target.write_bytes(raw)
        manifest[name] = {
            "path": str(target),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }

    for name, obj in objects.items():
        write(name, obj)
    return manifest, objects, write


def test_real_receipt_boundary_without_source_or_fit_claim(files):
    manifest, _, _ = files
    result = gate.check(manifest)
    assert result["receipt_check"] == "passed"
    assert result["source_completeness"] == result["context_fit"] == "not_checked"
    assert result["dispatch_authorized"] is False


@pytest.mark.parametrize(
    "field,value", [("role", "user"), ("tool_calls", [{"id": "x"}])]
)
def test_message_controls_reject_rehashed_software_mutation(files, field, value):
    manifest, objects, write = files
    record = copy.deepcopy(objects["receipt"])
    record["content"]["raw_response"]["message"][field] = value
    record["sha256"] = digest(record["content"])
    write("receipt", record)
    with pytest.raises(ValueError, match="Raw provider"):
        gate.check(manifest)


def test_missing_stop_refused_even_when_native_gate_accepts(files):
    manifest, objects, write = files
    record = copy.deepcopy(objects["receipt"])
    record["content"]["raw_response"].pop("done_reason")
    record["sha256"] = digest(record["content"])
    write("receipt", record)
    with pytest.raises(ValueError, match="Raw provider"):
        gate.check(manifest)


def test_stdout_and_host_lease_count_must_match(files):
    manifest, objects, write = files
    changed = copy.deepcopy(objects["stdout_result"])
    changed["text"] += "different"
    write("stdout_result", changed)
    with pytest.raises(ValueError, match="stdout"):
        gate.check(manifest)
    write("stdout_result", objects["stdout_result"])
    manifest["lease_handles_closed"] = 1
    with pytest.raises(ValueError, match="lease count"):
        gate.check(manifest)


def test_bad_file_pin_refused(files):
    manifest, _, _ = files
    manifest["request"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="checksum"):
        gate.check(manifest)
