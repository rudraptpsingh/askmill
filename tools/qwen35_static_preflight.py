"""Qualified CPU-only Qwen3.5 static fit for an explicitly pinned local plan.

Requires already qualified metadata/program pins. Starts no provider/Session.
Tokenization uses the zero-tensor sidecar, never the original model container.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from askmill import Request
from askmill.jsonio import load, read_bytes

from capacity_preflight import preflight, qualified_install


PIN_LIMIT = 256 * 1024 * 1024


def verify(record):
    path = Path(record["path"])
    if path.stat().st_size > PIN_LIMIT:
        raise ValueError("Qualification asset exceeds byte limit")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != record["sha256"] or path.stat().st_size != record["bytes"]:
        raise ValueError("Qualification asset pin mismatch: " + str(path))
    return path


def qualify(plan_path, expected_plan_sha256, output):
    raw = read_bytes(plan_path)
    if hashlib.sha256(raw).hexdigest() != expected_plan_sha256:
        raise ValueError("Plan checksum mismatch")
    plan = load(plan_path)
    if plan["schema_version"] != "askmill.offline-toolchain-plan.v1":
        raise ValueError("Unsupported qualification plan")
    if sys.platform != "darwin":
        raise ValueError("This qualification path requires the macOS sandbox")
    keys = [
        "registry",
        "candidate_request",
        "parent_frozen_request",
        "wheel",
        "original_model_manifest",
        "metadata_export",
        "metadata_sidecar",
        "provider_build",
        "provider",
        "renderer",
        "tokenizer",
    ]
    paths = {key: verify(plan[key]) for key in keys}
    for library in plan["tokenizer_libraries"]:
        verify(library)
    if plan["tokenizer_build_flags"] != {
        "GGML_METAL": "OFF",
        "GGML_CUDA": "OFF",
        "GGML_BACKEND_DL": "OFF",
    }:
        raise ValueError("Require qualified CPU-only tokenizer build")
    build = load(paths["provider_build"])
    if (
        not build["publisher_binary_verified"]
        or build["binary"] != plan["provider"]
        or build["source_commit"] != plan["renderer_source_commit"]
    ):
        raise ValueError("Official provider identity or upstream renderer pin missing")
    verify(build["llama_server"])
    install = qualified_install(paths["wheel"], plan["wheel"]["sha256"])
    baseline = preflight(
        paths["registry"],
        plan["profile"],
        paths["candidate_request"],
        install,
        paths["original_model_manifest"],
        plan["blob_directory"],
    )
    if baseline["request"]["schema_gate"] != "passed":
        raise ValueError("Candidate request/schema refused before tokenization")
    profile = baseline["profile"]
    request_raw = read_bytes(paths["candidate_request"])
    if (
        hashlib.sha256(request_raw).hexdigest() != plan["candidate_request"]["sha256"]
        or baseline["request"]["sha256"] != plan["candidate_request"]["sha256"]
        or baseline["profile"]["registry"]["sha256"] != plan["registry"]["sha256"]
    ):
        raise ValueError("Frozen inputs changed during qualification")
    request = Request.model_validate_json(request_raw)
    if (
        profile["provider"] != "ollama"
        or not profile["model"].startswith("qwen3.5:")
        or baseline["model_metadata"]["declared_renderer"] != "qwen3.5"
        or request.images
        or profile["generation"]["thinking"] is not False
    ):
        raise ValueError("Require Qwen3.5 single-user text/no-thinking scope")
    manifest = load(paths["original_model_manifest"])
    if any(
        item["mediaType"]
        not in {
            "application/vnd.ollama.image.model",
            "application/vnd.ollama.image.projector",
            "application/vnd.ollama.image.template",
            "application/vnd.ollama.image.params",
            "application/vnd.ollama.image.license",
        }
        for item in manifest["layers"]
    ):
        raise ValueError(
            "Model system/history/unknown layers require separate qualification"
        )
    export = load(paths["metadata_export"])
    models = [
        item["digest"].removeprefix("sha256:")
        for item in manifest["layers"]
        if item["mediaType"] == "application/vnd.ollama.image.model"
    ]
    if (
        models != [export["container"]["sha256"]]
        or export["sidecar"] != plan["metadata_sidecar"]
        or export["exported_tensor_count"] != 0
        or not export["all_metadata_field_bytes_preserved"]
    ):
        raise ValueError("Tokenizer metadata/container correspondence missing")
    native = export["metadata_fields"]["qwen35.context_length"]["summary"]
    if type(native) is not int or native < 1:
        raise ValueError("Unqualified native model context")
    registry = load(paths["registry"])
    deny = [export["container"]["path"]] + registry.get("lease_paths", [])
    rules = "(version 1)(allow default)(deny network*)" + "".join(
        "(deny file-read* file-write* (literal "
        + json.dumps(str(Path(p).resolve()))
        + "))"
        for p in deny
    )
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    prompt = output / "prompt.txt"
    prompt.write_bytes(request.prompt.encode())

    def invoke(arguments, name):
        target = output / name
        with (
            target.open("xb") as stdout,
            (output / (name + ".stderr")).open("xb") as stderr,
        ):
            result = subprocess.run(
                ["/usr/bin/sandbox-exec", "-p", rules] + list(map(str, arguments)),
                stdout=stdout,
                stderr=stderr,
                timeout=30,
            )
        if result.returncode:
            raise ValueError(
                "Offline helper failed; retained stderr: " + str(target) + ".stderr"
            )
        return target

    rendered = invoke([paths["renderer"], prompt, "false"], "rendered.txt")
    rendered_raw = read_bytes(rendered)
    counts = []
    for special in [0, 1]:
        record = load(
            invoke(
                [paths["tokenizer"], paths["metadata_sidecar"], rendered, special],
                "tokens-" + str(special) + ".json",
            ),
            32 * 1024 * 1024,
        )
        if (
            record["count"] != len(record["tokens"])
            or record["input_utf8_bytes"] != len(rendered_raw)
            or record["vocabulary_tokens"]
            != export["metadata_fields"]["tokenizer.ggml.tokens"]["summary"]["elements"]
        ):
            raise ValueError("Invalid tokenizer result binding")
        counts.append(record["count"])
    # Both provider tokenization and generation's add-special path are covered.
    input_bound = max(counts)
    for key in keys:
        verify(plan[key])
    for library in plan["tokenizer_libraries"]:
        verify(library)
    declared = profile["generation"]["context_tokens"]
    if declared is None:
        raise ValueError("Static fit requires an explicit declared context")
    effective_static_limit = min(declared, native)
    total = input_bound + request.max_tokens
    report = {
        "schema_version": "askmill.qwen35-static-qualification.v1",
        "evidence_scope": "qualified_upstream_renderer_static",
        "provider_source_to_binary_correspondence": "unproved",
        "actual_provider_prompt_eval_count": None,
        "plan": {
            "path": str(Path(plan_path).resolve()),
            "sha256": expected_plan_sha256,
        },
        "request": baseline["request"],
        "profile": profile,
        "validator": install,
        "parent_frozen_request": plan["parent_frozen_request"],
        "provider_build": plan["provider_build"],
        "provider": plan["provider"],
        "renderer": plan["renderer"],
        "tokenizer": plan["tokenizer"],
        "metadata_export": plan["metadata_export"],
        "metadata_sidecar": plan["metadata_sidecar"],
        "rendered": {
            "bytes": len(rendered_raw),
            "sha256": hashlib.sha256(rendered_raw).hexdigest(),
        },
        "tokens": {
            "provider_add_special_false": counts[0],
            "generation_add_special_true": counts[1],
            "exact_complete_input_tokens": counts[0]
            if counts[0] == counts[1]
            else None,
            "complete_input_upper_bound": input_bound,
            "parse_special": True,
        },
        "static_capacity": {
            "state": "fits_qualified_upstream_static_limit"
            if total <= effective_static_limit
            else "exceeds_qualified_upstream_static_limit",
            "native_context_limit": native,
            "declared_context": declared,
            "reserved_output_tokens": request.max_tokens,
            "total_reserved_tokens": total,
            "remaining_tokens": effective_static_limit - total,
        },
        "runtime_allocation_attestation": "not_performed",
        "boundaries": {
            "provider_started": False,
            "Session_initialized": False,
            "model_inference": 0,
            "original_container_read_during_this_count": False,
            "tensor_model_loaded": False,
            "gpu_leases_acquired_or_bypassed": False,
            "helper_network_denied_by_os_sandbox": True,
            "execution_authorized": False,
            "consumer_acceptance": "pending",
            "canonical_postvalidation_or_domain_approval": False,
        },
        "utility_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    with (output / "qualification.json").open("x") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = qualify(args.plan, args.plan_sha256, args.output)
    print(
        json.dumps(
            {
                "static_capacity": report["static_capacity"],
                "tokens": report["tokens"],
                "execution_authorized": False,
                "output": str(args.output / "qualification.json"),
            }
        )
    )


if __name__ == "__main__":
    main()
