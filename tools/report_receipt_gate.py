"""Offline report-phase receipt gate. No dispatch, source or fit approval."""

import argparse
import hashlib
import json
from pathlib import Path

from askmill import Profile, Request
from askmill.jsonio import MAX_RECEIPT_BYTES, loads, read_bytes
from askmill.runner import verify_cached_record


def pinned(ref, limit=MAX_RECEIPT_BYTES):
    if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
        raise ValueError("Invalid pinned file reference")
    raw = read_bytes(ref["path"], limit)
    if hashlib.sha256(raw).hexdigest() != ref["sha256"]:
        raise ValueError("Pinned file checksum mismatch")
    return loads(raw, limit)


def check(manifest):
    names = {
        "schema_version",
        "request",
        "profile",
        "runtime",
        "receipt",
        "settlement",
        "stdout_result",
        "lease_handles_closed",
    }
    if (
        set(manifest) != names
        or manifest["schema_version"] != "askmill.report-receipt-gate.v1"
    ):
        raise ValueError("Unsupported gate manifest")
    request = Request.model_validate(pinned(manifest["request"]))
    profile = Profile.model_validate(pinned(manifest["profile"]))
    runtime = pinned(manifest["runtime"])
    receipt = pinned(manifest["receipt"])
    settlement = pinned(manifest["settlement"])
    stdout = pinned(manifest["stdout_result"])
    if (
        request.schema_version != "askmill.request.v2"
        or request.images
        or profile.provider != "ollama"
        or profile.ownership != "external"
    ):
        raise ValueError("Gate requires text-only Ollama structured request")
    content = receipt["content"]
    result = verify_cached_record(
        receipt, content["key"], request.model_dump(), profile, runtime, settlement
    )
    if (
        stdout != content["result"]
        or result.replayed
        or result.status != "completed"
        or not result.complete
        or not result.response_validation.valid
    ):
        raise ValueError("Completed, non-replayed stdout and receipt result required")
    raw = content["raw_response"]
    message = raw.get("message")
    count = raw.get("eval_count")
    prompt_count = raw.get("prompt_eval_count")
    if (
        not isinstance(message, dict)
        or message.get("role") != "assistant"
        or message.get("content") != result.text
        or message.get("tool_calls") not in (None, [])
        or raw.get("model") != profile.model
        or raw.get("done") is not True
        or raw.get("done_reason") != "stop"
        or type(count) is not int
        or count < 0
        or count != result.generated_tokens
        or (
            prompt_count is not None
            and (type(prompt_count) is not int or prompt_count < 0)
        )
    ):
        raise ValueError("Raw provider response is not a complete text-only stop")
    closed = manifest["lease_handles_closed"]
    if (
        type(closed) is not int
        or closed < 1
        or settlement["content"]["lease_handles_closed"] != closed
    ):
        raise ValueError("Settlement lease count differs from host expectation")
    return {
        "schema_version": "askmill.report-receipt-gate-result.v1",
        "receipt_check": "passed",
        "receipt_id": result.receipt_id,
        "session_id": result.session_id,
        "generated_tokens": count,
        "prompt_tokens": prompt_count,
        "source_completeness": "not_checked",
        "context_fit": "not_checked",
        "origin_authority": "host_must_authenticate_pins",
        "domain_acceptance": "not_granted",
        "dispatch_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    manifest = pinned({"path": args.manifest, "sha256": args.manifest_sha256})
    result = check(manifest)
    with Path(args.output).open("x") as out:
        json.dump(result, out, sort_keys=True, indent=2)
        out.write("\n")


if __name__ == "__main__":
    main()
