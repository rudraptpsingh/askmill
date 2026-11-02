"""Host-owned, fail-closed orchestration for a single report phase.

This module does not discover or start a provider. The embedding host supplies
all authority, source, capacity, durable reservation, dispatch and receipt gates.
"""

import hashlib
import json
from dataclasses import dataclass

from askmill import Request
from askmill.jsonio import MAX_RECEIPT_BYTES, loads, read_bytes


def detached(value):
    """Copy JSON-shaped host data without retaining shared mutable objects."""
    return loads(json.dumps(value, allow_nan=False), MAX_RECEIPT_BYTES)


def receipt_identity(ref):
    if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
        raise ValueError("Invalid receipt reference")
    raw = read_bytes(ref["path"], MAX_RECEIPT_BYTES)
    if hashlib.sha256(raw).hexdigest() != ref["sha256"]:
        raise ValueError("Receipt pin mismatch")
    result = loads(raw, MAX_RECEIPT_BYTES)["content"]["result"]
    return result["receipt_id"], result["session_id"]


class PortRefusal(RuntimeError):
    pass


@dataclass(frozen=True)
class Phase:
    job_id: str
    name: str
    request_sha256: str
    profile_sha256: str


class ReportHostPort:
    """Per-attempt coordinator; restart/replay safety belongs to durable host."""

    def __init__(self, *, policy=None, journal=None, provider=None, receipt_gate=None):
        self.policy = policy
        self.journal = journal
        self.provider = provider
        self.receipt_gate = receipt_gate
        self._attempted = set()

    def run(self, phase, request_bytes):
        if not all((self.policy, self.journal, self.provider, self.receipt_gate)):
            raise PortRefusal("Host integrations are not configured")
        if (
            not isinstance(phase, Phase)
            or phase.name not in ("generate", "source_review")
            or not phase.job_id
        ):
            raise PortRefusal("Invalid report phase")
        if (
            not isinstance(request_bytes, bytes)
            or hashlib.sha256(request_bytes).hexdigest() != phase.request_sha256
        ):
            raise PortRefusal("Frozen request bytes differ")
        request = Request.model_validate_json(request_bytes)
        if request.schema_version != "askmill.request.v2" or request.images:
            raise PortRefusal("Report port requires a structured text request")
        key = (phase.job_id, phase.name)
        if key in self._attempted:
            raise PortRefusal("Phase already attempted in this process")
        # The host owns authentication and must independently verify authority,
        # complete context, exact request/profile fit and review prerequisites.
        if self.policy.authorize(phase, request_bytes) is not True:
            raise PortRefusal("Host authority, context or fit not qualified")
        # reserve must be durable and exclusive across processes/restarts; it
        # must refuse uncertain, previously started or completed work.
        reservation = self.journal.reserve(phase)
        if not isinstance(reservation, str) or not reservation:
            raise PortRefusal("Host reservation unavailable")
        self._attempted.add(key)
        try:
            manifest = detached(
                self.provider.invoke_once(phase, request_bytes, reservation)
            )
            if (
                manifest["request"]["sha256"] != phase.request_sha256
                or manifest["profile"]["sha256"] != phase.profile_sha256
            ):
                raise PortRefusal("Receipt gate manifest differs from phase pins")
            expected_identity = receipt_identity(manifest["receipt"])
            gate_manifest = detached(manifest)
            checked = detached(self.receipt_gate(gate_manifest))
            if gate_manifest != manifest:
                raise PortRefusal("Receipt gate mutated its manifest")
            if (
                checked.get("receipt_check") != "passed"
                or (checked.get("receipt_id"), checked.get("session_id"))
                != expected_identity
                or receipt_identity(manifest["receipt"]) != expected_identity
            ):
                raise PortRefusal("Receipt gate result differs from pinned receipt")
            checked["phase_binding"] = {
                "job_id": phase.job_id,
                "phase": phase.name,
                "request_sha256": phase.request_sha256,
                "profile_sha256": phase.profile_sha256,
                "receipt_sha256": manifest["receipt"]["sha256"],
                "receipt_id": expected_identity[0],
                "session_id": expected_identity[1],
            }
            # No caller receives a shared completion object.
            self.journal.complete(phase, reservation, detached(checked))
            return detached(checked)
        except BaseException:
            # Never retry: even a failed callback could follow actual dispatch.
            self.journal.uncertain(phase, reservation)
            raise
