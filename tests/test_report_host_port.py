"""Synthetic orchestration controls; callbacks do not qualify a real host."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from askmill import Request, ResponseSchema

spec = importlib.util.spec_from_file_location(
    "report_host_port",
    Path(__file__).resolve().parents[1] / "tools/report_host_port.py",
)
port = importlib.util.module_from_spec(spec)

sys.modules[spec.name] = port
spec.loader.exec_module(port)


@pytest.fixture
def phase_and_bytes():
    req = Request(
        schema_version="askmill.request.v2",
        prompt="software control",
        response_schema=ResponseSchema.from_schema(
            {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            }
        ),
    )
    raw = json.dumps(req.model_dump()).encode()
    return port.Phase(
        "job-1", "generate", hashlib.sha256(raw).hexdigest(), "a" * 64
    ), raw


class Policy:
    def __init__(self, allowed=True):
        self.allowed = allowed

    def authorize(self, phase, raw):
        return self.allowed


class Journal:
    def __init__(self):
        self.events = []

    def reserve(self, phase):
        self.events.append("reserve")
        return "exclusive-test-reservation"

    def complete(self, phase, reservation, result):
        self.events.append("complete")

    def uncertain(self, phase, reservation):
        self.events.append("uncertain")


class Provider:
    def __init__(self, tmp_path, fail=False):
        self.calls = 0
        self.fail = fail
        data = json.dumps(
            {
                "content": {
                    "result": {
                        "receipt_id": "fake-receipt",
                        "session_id": "fake-session",
                    }
                }
            }
        ).encode()
        path = tmp_path / "mock-receipt.json"
        path.write_bytes(data)
        self.receipt = {"path": str(path), "sha256": hashlib.sha256(data).hexdigest()}

    def invoke_once(self, phase, raw, reservation):
        self.calls += 1
        if self.fail:
            raise RuntimeError("synthetic interruption")
        return {
            "request": {"sha256": phase.request_sha256},
            "profile": {"sha256": phase.profile_sha256},
            "receipt": self.receipt,
        }


def test_default_closed(phase_and_bytes, tmp_path):
    with pytest.raises(port.PortRefusal, match="not configured"):
        port.ReportHostPort().run(*phase_and_bytes)


def test_unknown_fit_refuses_before_reservation_or_dispatch(phase_and_bytes, tmp_path):
    journal, provider = Journal(), Provider(tmp_path)
    adapter = port.ReportHostPort(
        policy=Policy(False),
        journal=journal,
        provider=provider,
        receipt_gate=lambda _: {},
    )
    with pytest.raises(port.PortRefusal, match="not qualified"):
        adapter.run(*phase_and_bytes)
    assert not journal.events and provider.calls == 0


def test_one_call_then_no_implicit_retry(phase_and_bytes, tmp_path):
    journal, provider = Journal(), Provider(tmp_path)
    adapter = port.ReportHostPort(
        policy=Policy(),
        journal=journal,
        provider=provider,
        receipt_gate=lambda _: {
            "receipt_check": "passed",
            "receipt_id": "fake-receipt",
            "session_id": "fake-session",
        },
    )
    assert adapter.run(*phase_and_bytes)["receipt_check"] == "passed"
    with pytest.raises(port.PortRefusal, match="already attempted"):
        adapter.run(*phase_and_bytes)
    assert provider.calls == 1 and journal.events == ["reserve", "complete"]


def test_failure_is_uncertain_and_never_retried(phase_and_bytes, tmp_path):
    journal, provider = Journal(), Provider(tmp_path, fail=True)
    adapter = port.ReportHostPort(
        policy=Policy(), journal=journal, provider=provider, receipt_gate=lambda _: {}
    )
    with pytest.raises(RuntimeError, match="interruption"):
        adapter.run(*phase_and_bytes)
    with pytest.raises(port.PortRefusal, match="already attempted"):
        adapter.run(*phase_and_bytes)
    assert provider.calls == 1 and journal.events == ["reserve", "uncertain"]


def test_frozen_request_mismatch_refused(phase_and_bytes, tmp_path):
    phase, raw = phase_and_bytes
    journal, provider = Journal(), Provider(tmp_path)
    adapter = port.ReportHostPort(
        policy=Policy(), journal=journal, provider=provider, receipt_gate=lambda _: {}
    )
    with pytest.raises(port.PortRefusal, match="Frozen request"):
        adapter.run(phase, raw + b" ")
    assert not journal.events and provider.calls == 0


def test_bad_receipt_is_uncertain_not_completed(phase_and_bytes, tmp_path):
    journal, provider = Journal(), Provider(tmp_path)

    def refusal(_):
        raise ValueError("synthetic receipt refusal")

    adapter = port.ReportHostPort(
        policy=Policy(), journal=journal, provider=provider, receipt_gate=refusal
    )
    with pytest.raises(ValueError, match="receipt refusal"):
        adapter.run(*phase_and_bytes)
    assert provider.calls == 1 and journal.events == ["reserve", "uncertain"]


def test_mutable_provider_cache_does_not_change_actual_gate_input(tmp_path):
    """Two self-contained software receipts, real receipt gate, synchronized refresh."""
    import copy
    import threading
    import uuid

    from askmill import Profile, Result
    from askmill.runner import digest

    gate_spec = importlib.util.spec_from_file_location(
        "actual_receipt_gate",
        Path(__file__).resolve().parents[1] / "tools/report_receipt_gate.py",
    )
    gate = importlib.util.module_from_spec(gate_spec)
    gate_spec.loader.exec_module(gate)

    def fixture(label):
        directory = tmp_path / label
        directory.mkdir()
        req = Request(
            schema_version="askmill.request.v2",
            prompt="software " + label,
            max_tokens=32,
            response_schema=ResponseSchema.from_schema(
                {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                }
            ),
        )
        profile = Profile(
            schema_version="askmill.profile.v2",
            provider="ollama",
            model="fixture",
            revision="a" * 64,
            capabilities=["text"],
            ownership="external",
            base_url="http://127.0.0.1:1",
        )
        runtime = {
            "askmill_version": "0.1.0a6",
            "lease_paths_sha256": digest(["fixture-a", "fixture-b"]),
        }
        request, profile_data = req.model_dump(), profile.model_dump()
        key = digest({"request": request, "profile": profile_data, "runtime": runtime})
        session = str(uuid.uuid4())
        result = Result(
            schema_version="askmill.result.v2",
            status="completed",
            text="{}",
            complete=True,
            model=profile.model,
            revision=profile.revision,
            generated_tokens=1,
            seconds=0.0,
            runtime=runtime,
            receipt_id=key,
            attempt_id=str(uuid.uuid4()),
            session_id=session,
            replayed=False,
            response_validation={
                "schema_version": "askmill.response-validation.v1",
                "schema_sha256": req.response_schema.sha256,
                "valid": True,
                "errors": [],
            },
        ).model_dump()
        raw_response = {
            "message": {"role": "assistant", "content": "{}"},
            "model": profile.model,
            "done": True,
            "done_reason": "stop",
            "eval_count": 1,
            "prompt_eval_count": 10,
        }
        content = {
            "schema_version": "askmill.receipt.v2",
            "key": key,
            "request": request,
            "profile": profile_data,
            "runtime": runtime,
            "result": result,
            "raw_response": raw_response,
        }
        settled = {
            "schema_version": "askmill.settlement.v2",
            "session_id": session,
            "worker_pid": 1,
            "worker_reaped": True,
            "ownership": "external",
            "external_service_stopped": False,
            "external_request_settlement": "acknowledged",
            "lease_handles_closed": 2,
            "quarantined": False,
            "profile_sha256": digest(profile_data),
            "lease_paths_sha256": runtime["lease_paths_sha256"],
            "runner_version": "0.1.0a6",
        }
        items = {
            "request": request,
            "profile": profile_data,
            "runtime": runtime,
            "receipt": {"content": content, "sha256": digest(content)},
            "settlement": {"content": settled, "sha256": digest(settled)},
            "stdout_result": result,
        }
        manifest = {
            "schema_version": "askmill.report-receipt-gate.v1",
            "lease_handles_closed": 2,
        }
        for name, value in items.items():
            path = directory / (name + ".json")
            data = json.dumps(value).encode()
            path.write_bytes(data)
            manifest[name] = {
                "path": str(path),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        return manifest, (directory / "request.json").read_bytes(), key

    manifest_a, request_a, key_a = fixture("a")
    manifest_b, _, key_b = fixture("b")
    cache = copy.deepcopy(manifest_a)
    entered, refreshed = threading.Event(), threading.Event()

    class CachedProvider:
        def invoke_once(self, *args):
            return cache

    def refresh():
        assert entered.wait(2)
        cache.clear()
        cache.update(copy.deepcopy(manifest_b))
        refreshed.set()

    def actual_gate(manifest):
        entered.set()
        assert refreshed.wait(2)
        return gate.check(manifest)

    thread = threading.Thread(target=refresh)
    thread.start()
    journal = Journal()
    phase = port.Phase(
        "job-a",
        "generate",
        hashlib.sha256(request_a).hexdigest(),
        manifest_a["profile"]["sha256"],
    )
    result = port.ReportHostPort(
        policy=Policy(),
        journal=journal,
        provider=CachedProvider(),
        receipt_gate=actual_gate,
    ).run(phase, request_a)
    thread.join()
    assert key_a != key_b and result["receipt_id"] == key_a
    assert result["phase_binding"]["receipt_id"] == key_a
    assert journal.events == ["reserve", "complete"]


def test_journal_cannot_mutate_returned_completion(phase_and_bytes, tmp_path):
    class MutatingJournal(Journal):
        def complete(self, phase, reservation, result):
            result["receipt_id"] = "mutated"
            result["phase_binding"]["receipt_id"] = "mutated"
            super().complete(phase, reservation, result)

    adapter = port.ReportHostPort(
        policy=Policy(),
        journal=MutatingJournal(),
        provider=Provider(tmp_path),
        receipt_gate=lambda _: {
            "receipt_check": "passed",
            "receipt_id": "fake-receipt",
            "session_id": "fake-session",
        },
    )
    result = adapter.run(*phase_and_bytes)
    assert (
        result["receipt_id"] == result["phase_binding"]["receipt_id"] == "fake-receipt"
    )


def test_gate_result_must_match_pinned_receipt(phase_and_bytes, tmp_path):
    journal = Journal()
    adapter = port.ReportHostPort(
        policy=Policy(),
        journal=journal,
        provider=Provider(tmp_path),
        receipt_gate=lambda _: {
            "receipt_check": "passed",
            "receipt_id": "different",
            "session_id": "fake-session",
        },
    )
    with pytest.raises(port.PortRefusal, match="differs from pinned receipt"):
        adapter.run(*phase_and_bytes)
    assert journal.events == ["reserve", "uncertain"]


def test_gate_mutation_refused(phase_and_bytes, tmp_path):
    journal = Journal()

    def mutate(manifest):
        manifest["request"]["sha256"] = "0" * 64
        return {
            "receipt_check": "passed",
            "receipt_id": "fake-receipt",
            "session_id": "fake-session",
        }

    adapter = port.ReportHostPort(
        policy=Policy(),
        journal=journal,
        provider=Provider(tmp_path),
        receipt_gate=mutate,
    )
    with pytest.raises(port.PortRefusal, match="mutated its manifest"):
        adapter.run(*phase_and_bytes)
    assert journal.events == ["reserve", "uncertain"]
