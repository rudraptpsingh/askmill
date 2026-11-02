"""Offline request/profile capacity evidence against a separately pinned wheel.

No Session, provider connection, tokenizer fallback or weight-file reads.
Unsupported tokenization yields unknown, never a byte-to-token estimate.
"""

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import time
from zipfile import ZipFile

import askmill
from askmill import Profile, Request
from askmill.jsonio import loads, read_bytes

META_LIMIT = 1024 * 1024
ALLOWED_METADATA = {
    "application/vnd.ollama.image.template",
    "application/vnd.ollama.image.params",
    "application/vnd.ollama.image.system",
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path, raw):
    return {"path": str(Path(path).resolve()), "sha256": sha(raw), "bytes": len(raw)}


def metadata_bytes(path):
    if Path(path).stat().st_size > META_LIMIT:
        raise ValueError("Metadata exceeds 1 MiB; file not opened")
    return read_bytes(path, META_LIMIT)


def qualified_install(wheel, expected_sha256):
    raw = metadata_bytes(wheel)
    if sha(raw) != expected_sha256:
        raise ValueError("Preflight wheel checksum mismatch")
    distribution = importlib.metadata.distribution("askmill")
    if "site-packages" not in Path(askmill.__file__).parts:
        raise ValueError(
            "Use a separately installed immutable wheel, not an editable checkout"
        )
    with ZipFile(wheel) as archive:
        names = [
            name
            for name in archive.namelist()
            if name.startswith("askmill/") and name.endswith(".py")
        ]
        for name in names:
            if ".." in Path(name).parts:
                raise ValueError("Unsafe wheel member")
            installed = Path(distribution.locate_file(name))
            if installed.read_bytes() != archive.read(name):
                raise ValueError("Installed module differs from pinned wheel: " + name)
    return {
        "version": distribution.version,
        "wheel": pin(wheel, raw),
        "installed_payload_matches": True,
    }


def ollama_metadata(profile, manifest, blobs):
    if profile.provider != "ollama":
        raise ValueError("Ollama manifest metadata requires an Ollama profile")
    raw = metadata_bytes(manifest)
    expected = profile.revision.removeprefix("sha256:")
    if sha(raw) != expected:
        raise ValueError(
            "Manifest bytes do not match profile revision; use the original content-addressed manifest"
        )
    document = loads(raw, META_LIMIT)
    layers = document.get("layers")
    if not isinstance(layers, list) or len(layers) > 32:
        raise ValueError("Invalid model metadata layer list")
    forbidden = {
        item.get("digest")
        for item in layers
        if isinstance(item, dict) and item.get("mediaType") not in ALLOWED_METADATA
    }

    def read_layer(item):
        digest = item.get("digest", "")
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest) or digest in forbidden:
            raise ValueError(
                "Refusing unqualified metadata layer or weight-container alias"
            )
        if type(item.get("size")) is not int or not 0 <= item["size"] <= META_LIMIT:
            raise ValueError("Refusing oversize metadata layer")
        path = Path(blobs) / digest.replace(":", "-", 1)
        data = metadata_bytes(path)
        if len(data) != item["size"] or sha(data) != digest.split(":", 1)[1]:
            raise ValueError("Metadata layer size/checksum mismatch")
        return path, data

    # Config is metadata, but must not alias any declared tensor container.
    config = document.get("config", {})
    config_path, config_raw = read_layer(config)
    config_data = loads(config_raw, META_LIMIT)
    observed = []
    defaults = None
    for item in layers:
        if not isinstance(item, dict):
            raise ValueError("Invalid metadata layer")
        if item.get("mediaType") in ALLOWED_METADATA:
            path, data = read_layer(item)
            observed.append({"media_type": item["mediaType"], **pin(path, data)})
            if item["mediaType"] == "application/vnd.ollama.image.params":
                defaults = loads(data, META_LIMIT)
    containers = [
        {
            "media_type": item.get("mediaType"),
            "declared_digest": item.get("digest"),
            "declared_bytes": item.get("size"),
            "file_opened": False,
        }
        for item in layers
        if item.get("mediaType")
        in {
            "application/vnd.ollama.image.model",
            "application/vnd.ollama.image.projector",
        }
    ]
    return {
        "manifest": pin(manifest, raw),
        "revision_matches_manifest": True,
        "config": pin(config_path, config_raw),
        "declared_renderer": config_data.get("renderer"),
        "declared_parser": config_data.get("parser"),
        "metadata_layers": observed,
        "model_default_parameters": defaults,
        "tokenizer_and_tensor_containers": containers,
        "tokenizer_identity": "embedded container digest only; tokenizer not extracted or qualified",
        "complete_provider_template_renderer": "not_qualified_offline",
        "native_model_context_limit": None,
        "weight_integrity_or_live_tag_identity_verified": False,
    }


def preflight(
    config,
    profile_name,
    request_path,
    install,
    manifest=None,
    blobs=None,
    execution_runtime=None,
):
    started = time.monotonic_ns()
    config_raw = read_bytes(config)
    registry = loads(config_raw)
    if registry.get("schema_version") != "askmill.profiles.v1":
        raise ValueError("Unsupported profile registry")
    profile = Profile.model_validate(registry["profiles"][profile_name])
    raw = read_bytes(request_path)
    body = loads(raw)
    if not isinstance(body, dict):
        raise ValueError("Request must be a JSON object")
    errors = []
    try:
        Request.model_validate_json(raw)
    except ValueError as error:
        if hasattr(error, "errors"):
            errors = [
                {
                    "location": list(item["loc"]),
                    "type": item["type"],
                    "message": item["msg"],
                }
                for item in error.errors(include_input=False, include_url=False)[:16]
            ]
        else:
            errors = [{"type": "invalid_input", "message": str(error)}]
    prompt = body.get("prompt")
    prompt_bytes = prompt.encode("utf-8") if isinstance(prompt, str) else None
    maximum = body.get("max_tokens", 2048)
    output_reserve = maximum if type(maximum) is int and 1 <= maximum <= 16384 else None
    selected_context = profile.generation.context_tokens if profile.generation else None
    budget = (
        (selected_context - output_reserve)
        if selected_context is not None and output_reserve is not None
        else None
    )
    metadata = None
    if manifest is not None:
        if blobs is None:
            raise ValueError("Supply blob directory with manifest")
        metadata = ollama_metadata(profile, manifest, blobs)
    runtime_ref = None
    if execution_runtime is not None:
        runtime_raw = metadata_bytes(execution_runtime)
        runtime = loads(runtime_raw, META_LIMIT)
        runtime_ref = {
            **pin(execution_runtime, runtime_raw),
            "declared_version": runtime.get("version"),
            "execution_runtime_not_started_or_requalified": True,
        }
    unsupported = "No qualified offline tokenizer plus complete provider renderer for this pinned profile; no character/byte ratio or exact token count inferred"
    return {
        "schema_version": "askmill.capacity-preflight.v1",
        "status": "request_rejected" if errors else "capacity_unknown",
        "preflight_install": install,
        "execution_runtime_ref": runtime_ref,
        "profile": {
            "name": profile_name,
            "provider": profile.provider,
            "model": profile.model,
            "revision": profile.revision,
            "generation": profile.generation.model_dump()
            if profile.generation
            else None,
            "profile_sha256": sha(profile.model_dump_json().encode()),
            "registry": pin(config, config_raw),
        },
        "request": {
            **pin(request_path, raw),
            "schema_gate": "rejected" if errors else "passed",
            "errors": errors,
            "prompt_sha256": sha(prompt_bytes) if prompt_bytes is not None else None,
            "prompt_utf8_bytes": len(prompt_bytes)
            if prompt_bytes is not None
            else None,
            "prompt_codepoints": len(prompt) if isinstance(prompt, str) else None,
            "source_count": len(body["sources"])
            if isinstance(body.get("sources"), list)
            else None,
            "image_count": len(body["images"])
            if isinstance(body.get("images"), list)
            else None,
            "response_schema_sha256": body["response_schema"].get("sha256")
            if isinstance(body.get("response_schema"), dict)
            else None,
        },
        "model_metadata": metadata,
        "provider_input_roles": {
            "prompt": "user message content; provider renderer adds model-specific framing",
            "sources": "frozen provenance metadata; AskMill does not add it to messages",
            "response_schema": "native Ollama format/grammar; schema text counts if caller separately includes it in prompt",
            "system_and_template_overhead": "unknown; template-layer pin alone does not qualify provider rendering",
            "thinking": profile.generation.thinking if profile.generation else False,
        },
        "tokenization": {
            "state": "unknown",
            "exact_input_tokens": None,
            "conservative_upper_bound": None,
            "justification": unsupported,
            "images_or_tokenizer_fallback_used": False,
            "missing_dependencies": {
                "revision_bound_tokenizer": {
                    "state": "unqualified",
                    "required": [
                        "Vocabulary, merge ranks and added/special-token IDs bound to the selected model revision",
                        "Pinned tokenizer implementation with normalization, pretokenization and BOS/EOS behavior",
                    ],
                },
                "complete_provider_rendering": {
                    "state": "unqualified",
                    "declared_renderer": metadata.get("declared_renderer")
                    if metadata
                    else None,
                    "required": [
                        "Provider build and full renderer/template implementation bound to that build",
                        "System/default messages, thinking settings and special-token framing for this exact request",
                    ],
                },
            },
        },
        "capacity": {
            "state": "unknown",
            "static_fit_state": "unknown",
            "runtime_allocation_attestation": "not_performed",
            "declared_profile_context_tokens": selected_context,
            "native_model_context_limit": None,
            "reserved_output_tokens": output_reserve,
            "input_budget_if_profile_context_is_honored": budget,
            "reservation_gate": "unknown"
            if budget is None
            else (
                "exceeds_declared_context" if budget < 0 else "within_declared_context"
            ),
            "allocation_or_complete_rendered_input_qualified": False,
            "missing_dependencies": [
                "Qualified complete rendered-input token count or conservative bound",
                "Native model context limit for static fit; runtime allocation is a separate later gate",
            ],
        },
        "boundaries": {
            "request_or_profile_changed": False,
            "execution_authorized": False,
            "Session_initialized": False,
            "provider_calls": 0,
            "model_leases_acquired": 0,
            "weights_loaded_or_read": False,
            "model_inference": 0,
            "tokenizer_or_provider_switched": False,
            "source_semantic_numeric_legal_or_client_approval": False,
        },
        "measurement": {
            "route": "offline metadata/schema preflight",
            "monotonic_elapsed_ns": time.monotonic_ns() - started,
            "performance_threshold_status": "not_established",
        },
        "utility_sha256": sha(Path(__file__).read_bytes()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--wheel-sha256", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--model-manifest", type=Path)
    parser.add_argument("--blob-directory", type=Path)
    parser.add_argument("--execution-runtime", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    install = qualified_install(args.wheel, args.wheel_sha256)
    result = preflight(
        args.config,
        args.profile,
        args.request,
        install,
        args.model_manifest,
        args.blob_directory,
        args.execution_runtime,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(
        json.dumps(
            {
                "status": result["status"],
                "capacity": result["capacity"],
                "output": str(args.output),
                "execution_authorized": False,
            }
        )
    )
    return 2 if result["status"] == "request_rejected" else 3


if __name__ == "__main__":
    raise SystemExit(main())
