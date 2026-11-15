"""Inspect retained AskMill/Ollama receipt timings without running a model."""
import argparse
import hashlib
import json
import math
from pathlib import Path

MAX_BYTES = 96 * 1024 * 1024
TIMING_FIELDS = ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration")
COUNT_FIELDS = ("prompt_eval_count", "prompt_eval_cached_count", "eval_count")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("Non-finite JSON number")


def _digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def inspect(raw, expected_sha256):
    """Return reported values and boundaries, not an authorization decision."""
    if len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Receipt size or expected SHA-256 mismatch")
    record = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    if not isinstance(record, dict) or set(record) != {"content", "sha256"}:
        raise ValueError("Unsupported receipt envelope")
    content = record["content"]
    if not isinstance(content, dict) or _digest_json(content) != record["sha256"]:
        raise ValueError("Receipt checksum mismatch")
    if content.get("schema_version") != "askmill.receipt.v2" or content.get("profile", {}).get("provider") != "ollama":
        raise ValueError("Expected a structured Ollama v2 receipt")
    result, runtime, response = content["result"], content["runtime"], content["raw_response"]
    key = _digest_json({name: content[name] for name in ("request", "profile", "runtime")})
    if content.get("key") != key or result.get("receipt_id") != key or result.get("runtime") != runtime or result.get("replayed") is not False:
        raise ValueError("Receipt input or result binding mismatch")
    seconds = result.get("seconds")
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
        raise ValueError("Invalid generation-attempt duration")
    if not isinstance(response, dict):
        raise ValueError("Missing provider response")
    def value(name):
        v = response.get(name)
        if v is not None and (type(v) is not int or v < 0):
            raise ValueError("Invalid provider counter: " + name)
        return v
    return {
        "schema_version": "askmill.generation-timing-inspection.v1",
        "receipt_sha256": expected_sha256,
        "receipt_id": key,
        "result_status": result.get("status"),
        "attempt_seconds": seconds,
        "attempt_boundary": "original generation attempt including provider call and post-call checks; excludes session startup and shutdown",
        "provider_duration_unit": "nanoseconds",
        "provider_reported_durations": {name: value(name) for name in TIMING_FIELDS},
        "provider_reported_counts": {name: value(name) for name in COUNT_FIELDS},
        "session_startup_seconds": None,
        "session_shutdown_seconds": None,
        "current_invocation_seconds": None,
        "current_invocation_replayed": None,
        "model_residency_before_call": "unknown",
        "interpretation": "Provider durations may overlap; no subtraction, cold/warm classification or output acceptance is inferred. Missing values are unknown.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--receipt-sha256", required=True)
    args = parser.parse_args()
    try:
        with Path(args.receipt).open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        print(json.dumps(inspect(raw, args.receipt_sha256), sort_keys=True, allow_nan=False))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, "timing inspection refused: " + type(exc).__name__ + "\n")


if __name__ == "__main__":
    main()
