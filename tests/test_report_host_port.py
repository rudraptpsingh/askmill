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
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def invoke_once(self, phase, raw, reservation):
        self.calls += 1
        if self.fail:
            raise RuntimeError("synthetic interruption")
        return {
            "request": {"sha256": phase.request_sha256},
            "profile": {"sha256": phase.profile_sha256},
        }


def test_default_closed(phase_and_bytes):
    with pytest.raises(port.PortRefusal, match="not configured"):
        port.ReportHostPort().run(*phase_and_bytes)


def test_unknown_fit_refuses_before_reservation_or_dispatch(phase_and_bytes):
    journal, provider = Journal(), Provider()
    adapter = port.ReportHostPort(
        policy=Policy(False),
        journal=journal,
        provider=provider,
        receipt_gate=lambda _: {},
    )
    with pytest.raises(port.PortRefusal, match="not qualified"):
        adapter.run(*phase_and_bytes)
    assert not journal.events and provider.calls == 0


def test_one_call_then_no_implicit_retry(phase_and_bytes):
    journal, provider = Journal(), Provider()
    adapter = port.ReportHostPort(
        policy=Policy(),
        journal=journal,
        provider=provider,
        receipt_gate=lambda _: {"receipt_check": "passed"},
    )
    assert adapter.run(*phase_and_bytes)["receipt_check"] == "passed"
    with pytest.raises(port.PortRefusal, match="already attempted"):
        adapter.run(*phase_and_bytes)
    assert provider.calls == 1 and journal.events == ["reserve", "complete"]


def test_failure_is_uncertain_and_never_retried(phase_and_bytes):
    journal, provider = Journal(), Provider(fail=True)
    adapter = port.ReportHostPort(
        policy=Policy(), journal=journal, provider=provider, receipt_gate=lambda _: {}
    )
    with pytest.raises(RuntimeError, match="interruption"):
        adapter.run(*phase_and_bytes)
    with pytest.raises(port.PortRefusal, match="already attempted"):
        adapter.run(*phase_and_bytes)
    assert provider.calls == 1 and journal.events == ["reserve", "uncertain"]


def test_frozen_request_mismatch_refused(phase_and_bytes):
    phase, raw = phase_and_bytes
    journal, provider = Journal(), Provider()
    adapter = port.ReportHostPort(
        policy=Policy(), journal=journal, provider=provider, receipt_gate=lambda _: {}
    )
    with pytest.raises(port.PortRefusal, match="Frozen request"):
        adapter.run(phase, raw + b" ")
    assert not journal.events and provider.calls == 0


def test_bad_receipt_is_uncertain_not_completed(phase_and_bytes):
    journal, provider = Journal(), Provider()

    def refusal(_):
        raise ValueError("synthetic receipt refusal")

    adapter = port.ReportHostPort(
        policy=Policy(), journal=journal, provider=provider, receipt_gate=refusal
    )
    with pytest.raises(ValueError, match="receipt refusal"):
        adapter.run(*phase_and_bytes)
    assert provider.calls == 1 and journal.events == ["reserve", "uncertain"]
