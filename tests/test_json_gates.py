"""Byte-boundary controls; optional real receipts stay outside the public repo."""

import copy
import json
import os
from pathlib import Path

import pytest

from askmill import Profile, Request
from askmill.jsonio import json_size, load, loads
from askmill.runner import RunError, digest, verify_cached_record


@pytest.fixture
def contract_bytes():
    # An actual shipped contract artifact, with no invented source/client data.
    return (
        Path(__file__).resolve().parents[1] / "schemas/request-v2.json"
    ).read_bytes()


def test_duplicate_keys_rejected_in_actual_contract_artifact(contract_bytes):
    value = json.loads(contract_bytes)
    duplicate = (
        contract_bytes.decode().rstrip()[:-1]
        + ',"title":'
        + json.dumps(value["title"])
        + "}"
    )
    with pytest.raises(ValueError, match="Duplicate JSON object key"):
        loads(duplicate)


def test_actual_contract_byte_budgets(contract_bytes, tmp_path):
    limit = len(contract_bytes) - 1
    with pytest.raises(ValueError, match="byte budget"):
        loads(contract_bytes, limit)
    path = tmp_path / "contract.json"
    path.write_bytes(contract_bytes)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="byte budget"):
        load(path, limit)
    assert path.read_bytes() == before


def test_streamed_json_budget_uses_actual_contract(contract_bytes):
    value = json.loads(contract_bytes)
    size = json_size(value, len(contract_bytes))
    with pytest.raises(ValueError, match="byte budget"):
        json_size(value, size - 1)


@pytest.fixture
def real_receipt():
    name = os.environ.get("ASKMILL_REAL_RECEIPT")
    if not name:
        pytest.skip("Supply an authorized actual receipt outside the public repository")
    path = Path(name)
    before = path.read_bytes()
    record = loads(before, 96 * 1024 * 1024)
    content = record["content"]
    settlement = load(
        path.parent / "settlements" / (content["result"]["session_id"] + ".json")
    )
    yield record, settlement
    assert path.read_bytes() == before


def test_real_request_duplicate_source_ids_rejected(real_receipt):
    record, _ = real_receipt
    body = copy.deepcopy(record["content"]["request"])
    assert body["sources"], "Choose an actual source-bound receipt"
    body["sources"] *= 2
    with pytest.raises(ValueError, match="Duplicate source IDs"):
        Request.model_validate(body)


def test_real_request_raw_duplicate_keys_rejected(real_receipt):
    record, _ = real_receipt
    body = record["content"]["request"]
    raw = json.dumps(body)[:-1] + ',"max_tokens":' + str(body["max_tokens"]) + "}"
    with pytest.raises(ValueError, match="Duplicate JSON object key"):
        Request.model_validate_json(raw)


@pytest.mark.parametrize(
    "field", ["model", "revision", "receipt_id", "runtime", "session_id"]
)
def test_real_replay_result_cross_binding_rejected(real_receipt, field):
    record, settlement = real_receipt
    original = record["content"]
    profile = Profile.model_validate(original["profile"])
    assert (
        verify_cached_record(
            record,
            original["key"],
            original["request"],
            profile,
            original["runtime"],
            settlement,
        ).receipt_id
        == original["key"]
    )
    changed = copy.deepcopy(record)
    result = changed["content"]["result"]
    if field == "runtime":
        result[field]["python"] += ".mismatch"
    elif field == "receipt_id":
        result[field] = "0" * 64
    else:
        result[field] += ".mismatch"
    changed["sha256"] = digest(changed["content"])
    with pytest.raises(RunError):
        verify_cached_record(
            changed,
            original["key"],
            original["request"],
            profile,
            original["runtime"],
            settlement,
        )


def test_real_replay_requires_acknowledged_settlement(real_receipt):
    record, settlement = real_receipt
    c = record["content"]
    profile = Profile.model_validate(c["profile"])
    with pytest.raises(RunError, match="no verified settlement"):
        verify_cached_record(record, c["key"], c["request"], profile, c["runtime"])
    bad = copy.deepcopy(settlement)
    bad["content"]["external_request_settlement"] = "unconfirmed"
    bad["sha256"] = digest(bad["content"])
    with pytest.raises(RunError, match="not settled"):
        verify_cached_record(record, c["key"], c["request"], profile, c["runtime"], bad)
