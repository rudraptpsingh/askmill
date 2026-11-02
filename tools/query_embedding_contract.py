"""Offline Query embedding-batch contract checks; never dispatches a model."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

from jsonschema import Draft202012Validator

from embedding_bridge import raw_pinned, strict_json

SCHEMA_PINS = {
    "request.schema.json": "04f81352a5d277f60b35c2599c3bc49a373c8d8149b61907e94a59e7ec6d8109",
    "response.schema.json": "97098d9c6d521393672ac4644554d9843cc4e050279dabb8b3400eccd04e491c",
}


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def validate_schema(name, document, schema_directory):
    schema = strict_json(
        raw_pinned(
            {
                "path": str(Path(schema_directory).resolve() / name),
                "sha256": SCHEMA_PINS[name],
            }
        )
    )
    Draft202012Validator(schema).validate(document)


def prepare(request_raw, askmill_profile_ref, schema_directory):
    request = strict_json(request_raw)
    validate_schema("request.schema.json", request, schema_directory)
    if len(request["items"]) > 32:
        raise ValueError("One-call host batch limit is 32; do not truncate")
    profile = request["profile"]
    if profile["dimensions"] != 768:
        raise ValueError("Wrong embedding dimensions")
    if askmill_profile_ref["sha256"] != profile["askmill_profile_sha256"]:
        raise ValueError("AskMill profile identity differs")
    raw_pinned(askmill_profile_ref)
    for ref_name, canonical_name in (
        ("provider_profile", "provider_profile_canonical_sha256"),
        ("model_input_profile", "model_input_profile_canonical_sha256"),
    ):
        value = strict_json(raw_pinned(profile[ref_name]))
        if digest(canonical(value)) != profile[canonical_name]:
            raise ValueError("Canonical model profile differs")
    raw_pinned(request["source_read_before"])
    ids = set()
    for row in request["items"]:
        if (
            row["id"] in ids
            or row["source_sha256"] != request["scope"]["sourceSha256"]
            or digest(row["embedding_input"].encode()) != row["embedding_input_sha256"]
        ):
            raise ValueError("Duplicate ID, source binding, or input hash mismatch")
        ids.add(row["id"])
    return {
        "schema": "askmill.query-embedding-inspection.v1",
        "request_sha256": digest(request_raw),
        "scope_sha256": digest(canonical(request["scope"])),
        "batch_id": request["batch_id"],
        "kind": request["kind"],
        "items": len(ids),
        "source_read_authority": "not_verified",
        "resource_policy": "not_verified",
        "dispatch_authorized": False,
    }


def verify_response(request_raw, result_raw, askmill_profile_ref, schema_directory):
    inspected = prepare(request_raw, askmill_profile_ref, schema_directory)
    request, result = strict_json(request_raw), strict_json(result_raw)
    validate_schema("response.schema.json", result, schema_directory)
    if (
        result["request_sha256"] != inspected["request_sha256"]
        or result["scope_sha256"] != inspected["scope_sha256"]
        or result["batch_id"] != request["batch_id"]
        or result["profile"] != request["profile"]
        or len(result["rows"]) != len(request["items"])
    ):
        raise ValueError("Response request, scope, profile or row count differs")
    for item, row in zip(request["items"], result["rows"]):
        values = row["values"]
        if (
            row["id"] != item["id"]
            or row["embedding_input_sha256"] != item["embedding_input_sha256"]
            or len(values) != 768
            or any(not math.isfinite(v) for v in values)
        ):
            raise ValueError("Response row identity, dimensions or values differ")
        try:
            packed = struct.pack("<768f", *values)
        except (OverflowError, struct.error) as exc:
            raise ValueError("Values exceed finite float32") from exc
        floats = struct.unpack("<768f", packed)
        if (
            any(not math.isfinite(v) for v in floats)
            or abs(math.sqrt(sum(v * v for v in floats)) - 1.0) >= 0.002
            or digest(packed) != row["vector_sha256"]
        ):
            raise ValueError("Vector float32 hash or normalization differs")
    for name in (
        "runtime_receipt",
        "model_usage_receipt",
        "resource_lease_receipt",
        "cleanup_receipt",
    ):
        raw_pinned(result[name])
    return {
        "schema": "askmill.query-embedding-response-inspection.v1",
        "response_contract": "passed",
        "request_sha256": inspected["request_sha256"],
        "scope_sha256": inspected["scope_sha256"],
        "rows": len(result["rows"]),
        "receipt_origins": "not_authenticated",
        "source_authority": "not_verified",
        "source_quality_approval": False,
        "legal_answer_eligible": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema-directory", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--request-sha256", required=True)
    parser.add_argument("--askmill-profile", required=True)
    parser.add_argument("--askmill-profile-sha256", required=True)
    parser.add_argument("--response")
    parser.add_argument("--response-sha256")
    args = parser.parse_args()
    request = raw_pinned({"path": args.request, "sha256": args.request_sha256})
    profile = {"path": args.askmill_profile, "sha256": args.askmill_profile_sha256}
    if (args.response is None) != (args.response_sha256 is None):
        parser.error("response and response-sha256 must be supplied together")
    result = (
        prepare(request, profile, args.schema_directory)
        if args.response is None
        else verify_response(
            request,
            raw_pinned({"path": args.response, "sha256": args.response_sha256}),
            profile,
            args.schema_directory,
        )
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
