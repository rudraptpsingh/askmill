"""Explicit, host-gated batch embeddings via a pinned Query encoder adapter.

No model discovery, automatic retry or fallback. The caller must authenticate
its source-read grant and resource decision independently before invocation.
"""

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys

MAX_JSON = 8 * 1024 * 1024
MAX_BATCH = 32


def raw_pinned(ref):
    if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
        raise ValueError("Expected exact path/SHA256 reference")
    path = Path(ref["path"])
    if not path.is_absolute():
        raise ValueError("Pinned paths must be absolute")
    with path.open("rb") as f:
        raw = f.read(MAX_JSON + 1)
    if len(raw) > MAX_JSON or hashlib.sha256(raw).hexdigest() != ref["sha256"]:
        raise ValueError("Pinned file size or checksum differs")
    return raw


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    return json.loads(
        raw,
        object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite JSON")),
    )


def request_check(request):
    if (
        set(request) != {"schema_version", "mode", "inputs", "source_read_ref"}
        or request["schema_version"] != "askmill.embedding-request.v1"
        or request["mode"] not in ("documents", "queries")
    ):
        raise ValueError("Unsupported embedding request")
    raw_pinned(request["source_read_ref"])
    rows = request["inputs"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_BATCH:
        raise ValueError("Batch must contain 1 to 32 rows")
    seen = set()
    for row in rows:
        if (
            not isinstance(row, dict)
            or set(row) != {"id", "text", "sha256"}
            or not isinstance(row["id"], str)
            or not row["id"]
            or row["id"] in seen
            or not isinstance(row["text"], str)
            or not row["text"]
            or len(row["text"].encode()) > 256 * 1024
            or hashlib.sha256(row["text"].encode()).hexdigest() != row["sha256"]
        ):
            raise ValueError("Invalid exact input or digest")
        seen.add(row["id"])
    return rows


def run_batch(registry, name, request, output):
    rows = request_check(request)
    if (
        set(registry) != {"schema_version", "profiles"}
        or registry["schema_version"] != "askmill.embedding-registry.v1"
        or name not in registry["profiles"]
    ):
        raise ValueError("Embedding profile not registered")
    entry = registry["profiles"][name]
    if set(entry) != {"adapter", "configuration", "dependencies", "source_gate"}:
        raise ValueError("Invalid profile entry")
    raw_pinned(entry["adapter"])
    raw_pinned(entry["source_gate"])
    config = strict_json(raw_pinned(entry["configuration"]))
    # Host-selected gate must authenticate the current source grant and exact
    # source/workspace scope; a pinned JSON file alone does not prove authority.
    gate_spec = importlib.util.spec_from_file_location(
        "askmill_explicit_source_gate", entry["source_gate"]["path"]
    )
    gate = importlib.util.module_from_spec(gate_spec)
    gate_spec.loader.exec_module(gate)
    if gate.verify_source_read(request, config) is not True:
        raise ValueError("Current host source-read grant is not authorized")
    dependencies = entry["dependencies"]
    if not isinstance(dependencies, list):
        raise ValueError("Require pinned adapter dependencies")
    for ref in dependencies:
        raw_pinned(ref)
    adapter_parent = Path(entry["adapter"]["path"]).parent
    host_parent = Path(config["host_scripts"])
    required = {
        str(adapter_parent / "cerc_resources.py"),
        str(host_parent / "run_regulatory_local_embeddings.py"),
        str(host_parent / "prepare_regulatory_local_embedding_inputs.py"),
        str(host_parent / "plan_regulatory_best_effort_embeddings.py"),
    }
    if not required.issubset({ref["path"] for ref in dependencies}):
        raise ValueError("Missing pinned host adapter dependency")
    if any(
        name in sys.modules
        for name in (
            "cerc_resources",
            "run_regulatory_local_embeddings",
            "prepare_regulatory_local_embedding_inputs",
            "plan_regulatory_best_effort_embeddings",
        )
    ):
        raise ValueError("Refusing preloaded encoder modules")
    # The existing Query adapter verifies the exact provider/model input profiles,
    # tokenizer, original host implementation and approved resource decision.
    # Refuse its ungated, legacy path and never invent a decision.
    if bool(config.get("resource_policy")) == bool(config.get("live_query_policy")):
        raise ValueError("Require exactly one explicit host resource policy")
    expected_profile = strict_json(raw_pinned(config["provider_profile"]))
    if (
        expected_profile.get("model") != "embeddinggemma-2:270m"
        or expected_profile.get("provider") != "ollama_local_mlx_nvfp4"
        or expected_profile.get("dimensions") != 768
        or expected_profile.get("max_context_tokens") != 8192
        or expected_profile.get("pooling") != "mean"
        or expected_profile.get("normalized") is not True
        or expected_profile.get("tokenizer_sha256")
        != "4d777ef5bdc1aa36227abdfb77c3e49e7b9c892d16e1b6bda41c393504828be4"
        or expected_profile.get("runtime", {}).get("api_model_digest")
        != "20c5a2af114e1813484d1611b27a57c33398aee4f59c39359c5a28af9d1547e7"
    ):
        raise ValueError("Unsupported pinned model space")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "RESERVED.json").write_text(
        json.dumps(
            {
                "state": "started_no_automatic_retry",
                "input_sha256s": [r["sha256"] for r in rows],
            }
        )
        + "\n"
    )
    adapter = Path(entry["adapter"]["path"])
    sys.path.insert(0, str(adapter.parent))
    spec = importlib.util.spec_from_file_location(
        "askmill_explicit_query_encoder", adapter
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    planned = {"documents": [], "queries": []}
    planned[request["mode"]] = [r["text"] for r in rows]
    # Exactly one encode invocation, at most one provider batch of <=32 rows.
    with module.encoder_session(config, output, planned_inputs=planned) as (
        profile,
        encode,
    ):
        if profile != expected_profile:
            raise ValueError("Provider profile differs from frozen expectation")
        matrix, native = encode(planned[request["mode"]], output, "batch")
        if (
            native.get("model_calls") != 1
            or native.get("inputs") != len(rows)
            or native.get("silent_truncation") is not False
        ):
            raise ValueError("Provider batch count or truncation evidence differs")
        import numpy as np

        if tuple(matrix.shape) != (len(rows), 768):
            raise ValueError("Unexpected vector shape")
        vectors = np.asarray(matrix, dtype="<f4")
        calculated_hashes = []
        for vector in vectors:
            if not all(math.isfinite(float(v)) for v in vector):
                raise ValueError("Non-finite vector")
            if abs(float(np.linalg.norm(vector)) - 1.0) >= 0.002:
                raise ValueError("Vector is not normalized")
            calculated_hashes.append(hashlib.sha256(vector.tobytes()).hexdigest())
        events = native.get("events")
        if (
            native.get("Float32_row_sha256s") != calculated_hashes
            or not isinstance(events, list)
            or len(events) != 1
            or events[0].get("input_sha256s") != [r["sha256"] for r in rows]
            or type(events[0].get("actual_tokens")) is not int
            or events[0]["actual_tokens"] <= 0
            or events[0].get("actual_provider_receipt", {}).get("prompt_eval_count")
            != events[0]["actual_tokens"]
        ):
            raise ValueError("Output rows or actual token evidence differ")
        values_ref = native.get("values")
        expected_path = output / "batch.npy"
        if (
            not isinstance(values_ref, dict)
            or values_ref.get("path") != str(expected_path)
            or hashlib.sha256(expected_path.read_bytes()).hexdigest()
            != values_ref.get("sha256")
        ):
            raise ValueError("Vector artifact pin differs")
        saved = np.load(expected_path, allow_pickle=False)
        if (
            saved.dtype != vectors.dtype
            or saved.shape != vectors.shape
            or not np.array_equal(saved, vectors)
        ):
            raise ValueError("Stored vector rows differ")
    for ref in [
        entry["adapter"],
        entry["configuration"],
        entry["source_gate"],
        *dependencies,
    ]:
        raw_pinned(ref)
    cleanup = strict_json((output / "cleanup.json").read_bytes())
    if (
        cleanup.get("owned_server_stopped") is not True
        or cleanup.get("unload_verified") is not True
    ):
        raise ValueError("Owned provider cleanup is not acknowledged")
    result = {
        "schema_version": "askmill.embedding-receipt.v1",
        "profile": name,
        "provider_profile_sha256": config["provider_profile"]["sha256"],
        "configuration_sha256": entry["configuration"]["sha256"],
        "adapter_sha256": entry["adapter"]["sha256"],
        "source_gate_sha256": entry["source_gate"]["sha256"],
        "source_read_ref": request["source_read_ref"],
        "model": expected_profile["model"],
        "dimensions": 768,
        "inputs": [
            {"id": row["id"], "sha256": row["sha256"], "float32_row_sha256": h}
            for row, h in zip(rows, native["Float32_row_sha256s"])
        ],
        "provider_model_calls": 1,
        "no_truncation": True,
        "source_authority": "host_verified_separately",
        "source_quality_approval": False,
        "legal_answer_eligible": False,
        "native_receipt": {
            "path": str(output / "batch-receipt.json"),
            "sha256": hashlib.sha256(
                (output / "batch-receipt.json").read_bytes()
            ).hexdigest(),
        },
        "vectors": native["values"],
        "cleanup": cleanup,
    }
    if len(result["inputs"]) != len(rows):
        raise ValueError("Missing output row hashes")
    path = output / "receipt.json"
    with path.open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list")
    listing.add_argument("--registry", required=True)
    listing.add_argument("--registry-sha256", required=True)
    run = sub.add_parser("embed")
    for key in (
        "registry",
        "registry-sha256",
        "profile",
        "request",
        "request-sha256",
        "output",
    ):
        run.add_argument("--" + key, required=True)
    args = parser.parse_args()
    registry = strict_json(
        raw_pinned({"path": args.registry, "sha256": args.registry_sha256})
    )
    if args.command == "list":
        if registry.get("schema_version") != "askmill.embedding-registry.v1":
            raise ValueError("Unsupported registry")
        print(
            json.dumps(
                {
                    "capability": "embedding",
                    "profiles": sorted(registry["profiles"]),
                    "registered_only": True,
                }
            )
        )
    else:
        req = strict_json(
            raw_pinned({"path": args.request, "sha256": args.request_sha256})
        )
        result = run_batch(registry, args.profile, req, args.output)
        print(
            json.dumps(
                {
                    "status": "completed",
                    "receipt": str(Path(args.output).resolve() / "receipt.json"),
                    "rows": len(result["inputs"]),
                }
            )
        )


if __name__ == "__main__":
    main()
