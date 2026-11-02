"""Host-owned, fail-closed orchestration for a single report phase.

This module does not discover or start a provider. The embedding host supplies
all authority, source, capacity, durable reservation, dispatch and receipt gates.
"""

import hashlib
from dataclasses import dataclass

from askmill import Request


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
            manifest = self.provider.invoke_once(phase, request_bytes, reservation)
            if (
                manifest["request"]["sha256"] != phase.request_sha256
                or manifest["profile"]["sha256"] != phase.profile_sha256
            ):
                raise PortRefusal("Receipt gate manifest differs from phase pins")
            checked = self.receipt_gate(manifest)
            if checked.get("receipt_check") != "passed":
                raise PortRefusal("Receipt gate refused")
            # Complete means the provider evidence passed, not domain acceptance.
            self.journal.complete(phase, reservation, checked)
            return checked
        except BaseException:
            # Never retry: even a failed callback could follow actual dispatch.
            self.journal.uncertain(phase, reservation)
            raise
