"""Project retained AskMill evidence into Map intake 1.1, without inference.

Portable references are caller-authorized, byte-pinned local evidence. This is
reporting, not source truth, reviewer authentication or legal acceptance.
"""

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re

from askmill import Result
from askmill.jsonio import loads, read_bytes

VERSION = "0.1.0"
LIMIT = 96 * 1024 * 1024
HEX = re.compile(r"^[a-f0-9]{64}$")
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def closed(value, required, optional=()):
    require(isinstance(value, dict), "Object required")
    require(
        set(required) <= value.keys() and value.keys() <= set(required) | set(optional),
        "Missing or unknown projection fields",
    )


def pointer(value, path):
    require(
        isinstance(path, str) and path.startswith("/"), "Explicit JSON pointer required"
    )
    for segment in path[1:].split("/"):
        key = segment.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            require(
                key.isdigit() and str(int(key)) == key,
                "Canonical array pointer index required",
            )
            value = value[int(key)]
        else:
            value = value[key]
    return value


def number(value, integer=False):
    if value is None:
        return None
    require(
        type(value) is int if integer else type(value) in (int, float),
        "Counter must be a number or null",
    )
    require(math.isfinite(value) and value >= 0, "Counter must be finite/nonnegative")
    return value


def reference(ref, roots):
    closed(ref, ("repository", "path", "sha256"), ("subject_pointer",))
    require(
        isinstance(ref["repository"], str) and ID.fullmatch(ref["repository"]),
        "Invalid repository",
    )
    require(
        isinstance(ref["sha256"], str) and HEX.fullmatch(ref["sha256"]),
        "Full reference SHA256 required",
    )
    relative = PurePosixPath(ref["path"])
    require(
        not relative.is_absolute()
        and ".." not in relative.parts
        and "\\" not in ref["path"],
        "Portable bounded evidence path required",
    )
    require(ref["repository"] in roots, "Evidence repository not authorized")
    root = Path(roots[ref["repository"]]).resolve()
    path = (root / relative).resolve()
    require(
        root in path.parents and path.is_file(),
        "Evidence missing or outside authorized root",
    )
    raw = read_bytes(path, LIMIT)
    require(sha(raw) == ref["sha256"], "Evidence byte pin mismatch")
    return loads(raw, LIMIT)


def envelope(ref, roots):
    wrapper = reference(ref, roots)
    closed(wrapper, ("content", "sha256"))
    require(
        sha(canonical(wrapper["content"])) == wrapper["sha256"],
        "Native envelope integrity mismatch",
    )
    return wrapper["content"]


def source_binding(request, binding, originals):
    closed(
        binding,
        (
            "prompt_json_byte_start",
            "prompt_json_byte_length",
            "json_sha256",
            "subject_pointers",
        ),
    )
    start, length = (
        binding["prompt_json_byte_start"],
        binding["prompt_json_byte_length"],
    )
    require(
        type(start) is int and type(length) is int and start >= 0 and length > 0,
        "Exact structured source byte range required",
    )
    prompt = request["prompt"].encode("utf-8")
    require(
        start + length <= len(prompt), "Structured source range exceeds frozen prompt"
    )
    raw = prompt[start : start + length]
    require(sha(raw) == binding["json_sha256"], "Structured source byte pin mismatch")
    value = loads(raw)
    subjects = binding["subject_pointers"]
    require(
        isinstance(subjects, list) and 1 <= len(subjects) <= 128,
        "Bounded source subject pointers required",
    )
    observed = {pointer(value, item) for item in subjects}
    require(
        observed == set(originals),
        "Frozen prompt source subjects differ from attributed originals",
    )
    return sha(canonical(binding))


def review_value(value, receipt_sha, roots, not_run=False):
    if value is None:
        return {
            "status": "not_run" if not_run else "pending",
            "accepted_candidates": None,
            "rejected_candidates": None,
            "unreviewed_candidates": None,
        }
    closed(value, ("receipt", "pointer", "target_pointer"))
    document = reference(value["receipt"], roots)
    reviewed = pointer(document, value["pointer"])
    closed(
        reviewed,
        (
            "status",
            "reviewer",
            "accepted_candidates",
            "rejected_candidates",
            "unreviewed_candidates",
        ),
    )
    require(
        reviewed["status"] in ("accepted", "rejected", "partial"),
        "Exact reviewed outcome required",
    )
    require(
        isinstance(reviewed["reviewer"], str) and reviewed["reviewer"],
        "Named caller reviewer required",
    )
    require(
        pointer(document, value["target_pointer"]) == receipt_sha,
        "Review targets different invocation evidence",
    )
    return {
        "status": reviewed["status"],
        "reviewer": reviewed["reviewer"],
        "receipt": value["receipt"],
    } | {
        key: number(reviewed[key], True)
        for key in (
            "accepted_candidates",
            "rejected_candidates",
            "unreviewed_candidates",
        )
    }


def project(descriptor, roots):
    closed(
        descriptor,
        (
            "schema_version",
            "run_id_prefix",
            "pipeline_run_id",
            "recorded_at",
            "requirements_sha256",
            "primary_document_sha256",
            "documents",
            "invocation",
        ),
        ("review", "extra_pins"),
    )
    require(
        descriptor["schema_version"] == "askmill.tracker-projection.v1",
        "Projection version mismatch",
    )
    for key in ("run_id_prefix", "pipeline_run_id"):
        require(
            isinstance(descriptor[key], str) and ID.fullmatch(descriptor[key]),
            "Safe run/pipeline ID required",
        )
    stamp = datetime.fromisoformat(descriptor["recorded_at"].replace("Z", "+00:00"))
    require(stamp.tzinfo is not None, "Recorded timestamp requires timezone")
    require(
        HEX.fullmatch(descriptor["requirements_sha256"]),
        "Requirements byte SHA required",
    )
    docs = descriptor["documents"]
    require(
        isinstance(docs, list) and 1 <= len(docs) <= 128,
        "Bounded actual document list required",
    )
    for doc in docs:
        closed(
            doc, ("sha256", "title", "profile_id", "body", "original_receipt", "holds")
        )
        require(HEX.fullmatch(doc["sha256"]), "Original document SHA256 required")
        require(
            all(
                isinstance(doc[k], str) and doc[k]
                for k in ("title", "profile_id", "body")
            ),
            "Document assignment required",
        )
        require(
            all(ID.fullmatch(doc[k]) for k in ("profile_id", "body")),
            "Safe profile/body required",
        )
        require(
            isinstance(doc["holds"], list)
            and all(isinstance(x, str) and x for x in doc["holds"]),
            "Explicit holds required",
        )
        original = reference(doc["original_receipt"], roots)
        require(
            pointer(original, doc["original_receipt"].get("subject_pointer"))
            == doc["sha256"],
            "Original receipt subject mismatch",
        )
    originals = sorted(doc["sha256"] for doc in docs)
    require(
        len(set(originals)) == len(originals)
        and descriptor["primary_document_sha256"] in originals,
        "Unique originals and bound primary document required",
    )
    inv = descriptor["invocation"]
    require(isinstance(inv, dict), "Invocation required")
    times = dict.fromkeys(
        (
            "invocation_wall_seconds",
            "session_run_seconds",
            "model_seconds",
            "load_seconds",
            "prefill_seconds",
            "generation_seconds",
            "preflight_seconds",
        )
    )
    tokens = dict.fromkeys(
        ("input", "output", "reserved_output", "declared_context", "allocated_context")
    )
    pins = {"requirements_sha256": descriptor["requirements_sha256"]}
    settlement_ref = None
    replay_ref = None
    if inv.get("kind") == "model_receipt":
        closed(
            inv,
            ("kind", "receipt", "source_binding"),
            ("result", "settlement", "allocated_context"),
        )
        content = envelope(inv["receipt"], roots)
        native = Result.model_validate(content["result"]).model_dump()
        require(
            content["key"] == native["receipt_id"], "Receipt/result identity mismatch"
        )
        require(
            content["key"]
            == sha(
                canonical(
                    {key: content[key] for key in ("request", "profile", "runtime")}
                )
            ),
            "Receipt key differs from frozen input/profile/runtime",
        )
        require(
            not native["model"].startswith("fixture:")
            and "synthetic" not in native["revision"],
            "Synthetic model evidence is not an eligible retained source run",
        )
        observed = reference(inv["result"], roots) if inv.get("result") else native
        observed = Result.model_validate(observed).model_dump()
        require(
            {k: v for k, v in observed.items() if k != "replayed"}
            == {k: v for k, v in native.items() if k != "replayed"},
            "Invocation result differs from native receipt",
        )
        replayed = observed["replayed"]
        require(
            not native["replayed"],
            "Native model receipt must identify original attempt",
        )
        invocation_id = (
            "replay-" + inv["result"]["sha256"] if replayed else native["attempt_id"]
        )
        request, profile = content["request"], content["profile"]
        if native.get("response_validation"):
            require(
                native["response_validation"]["schema_sha256"]
                == request.get("response_schema", {}).get("sha256"),
                "Output validation belongs to a different response schema",
            )
        require(
            request.get("images") == [], "Current reporting qualification is text-only"
        )
        status = "completed" if native["complete"] else "incomplete"
        complete = native["complete"]
        valid = (
            native.get("response_validation", {}).get("valid")
            if native.get("response_validation")
            else None
        )
        version = content["runtime"].get("askmill_version")
        require(
            isinstance(version, str) and version, "Native producer version required"
        )
        raw = content.get("raw_response", {})
        tokens.update(
            input=number(raw.get("prompt_eval_count"), True),
            output=number(raw.get("eval_count", native["generated_tokens"]), True),
            reserved_output=number(request["max_tokens"], True),
            declared_context=number(
                (profile.get("generation") or {}).get("context_tokens"), True
            ),
        )
        if raw.get("eval_count") is not None:
            require(
                raw["eval_count"] == native["generated_tokens"],
                "Provider/output token binding mismatch",
            )
        times["session_run_seconds"] = number(native["seconds"])
        for target, field in [
            ("model_seconds", "total_duration"),
            ("load_seconds", "load_duration"),
            ("prefill_seconds", "prompt_eval_duration"),
            ("generation_seconds", "eval_duration"),
        ]:
            ns = number(raw.get(field))
            times[target] = ns / 1e9 if ns is not None else None
        if replayed:
            replay_ref = inv["receipt"]
            tokens.update(input=0, output=0)
            times = {
                key: (
                    0
                    if key
                    in (
                        "model_seconds",
                        "load_seconds",
                        "prefill_seconds",
                        "generation_seconds",
                    )
                    else None
                )
                for key in times
            }
        if inv.get("allocated_context"):
            ctx = inv["allocated_context"]
            closed(ctx, ("receipt", "pointer", "revision_pointer"))
            evidence = reference(ctx["receipt"], roots)
            require(
                pointer(evidence, ctx["revision_pointer"]) == profile["revision"],
                "Allocation model revision mismatch",
            )
            tokens["allocated_context"] = number(
                pointer(evidence, ctx["pointer"]), True
            )
            pins["allocation_evidence_sha256"] = ctx["receipt"]["sha256"]
        if inv.get("settlement"):
            settled = envelope(inv["settlement"], roots)
            if replayed:
                require(
                    settled["session_id"] != native["session_id"],
                    "Cached-origin settlement is not current replay cleanup",
                )
            else:
                require(
                    settled["session_id"] == native["session_id"],
                    "Settlement session mismatch",
                )
                if settled.get("profile_sha256"):
                    require(
                        settled["profile_sha256"] == sha(canonical(profile)),
                        "Settlement profile mismatch",
                    )
            settlement_ref = inv["settlement"]
        calls = 0 if replayed else 1
        attempt, receipt_id = native["attempt_id"], native["receipt_id"]
        pins.update(
            request_snapshot_sha256=sha(canonical(request)),
            profile_sha256=sha(canonical(profile)),
        )
        if native.get("response_validation"):
            pins["provider_response_schema_sha256"] = native["response_validation"][
                "schema_sha256"
            ]
        receipt_ref = inv.get("result") or inv["receipt"]
        stage_status = "failed" if valid is False else ("done" if complete else "held")
    elif inv.get("kind") == "pre_dispatch_failure":
        closed(
            inv,
            (
                "kind",
                "receipt",
                "model_calls_pointer",
                "request",
                "profile_registry",
                "profile_name",
                "runtime",
                "source_binding",
            ),
        )
        failure = reference(inv["receipt"], roots)
        observed_calls = pointer(failure, inv["model_calls_pointer"])
        require(
            type(observed_calls) is int and observed_calls == 0,
            "Pre-dispatch failure needs observed zero-call proof",
        )
        request = reference(inv["request"], roots)
        profile = reference(inv["profile_registry"], roots)["profiles"][
            inv["profile_name"]
        ]
        runtime = reference(inv["runtime"], roots)
        version = runtime["version"]
        require(
            request.get("images") == [], "Current reporting qualification is text-only"
        )
        tokens.update(
            reserved_output=number(request["max_tokens"], True),
            declared_context=number(
                (profile.get("generation") or {}).get("context_tokens"), True
            ),
        )
        times["model_seconds"] = 0
        pins.update(
            request_sha256=inv["request"]["sha256"],
            profile_registry_sha256=inv["profile_registry"]["sha256"],
            runtime_sha256=inv["runtime"]["sha256"],
        )
        invocation_id = "refusal-" + inv["receipt"]["sha256"]
        attempt = receipt_id = None
        receipt_ref = inv["receipt"]
        calls = 0
        complete = valid = None
        status = "failed"
        stage_status = "failed"
        replayed = False
    else:
        raise ValueError("Unknown retained invocation kind")
    pins["source_binding_sha256"] = source_binding(
        request, inv["source_binding"], originals
    )
    for key, ref in descriptor.get("extra_pins", {}).items():
        require(
            ID.fullmatch(key) and key not in pins, "Invalid or duplicate extra pin name"
        )
        reference(ref, roots)
        pins[key] = ref["sha256"]
    run = {
        "invocation_id": invocation_id,
        "attempt_id": attempt,
        "receipt_id": receipt_id,
        "receipt": receipt_ref,
        "replayed": replayed,
        "primary_document_sha256": descriptor["primary_document_sha256"],
        "source_document_sha256s": originals,
        "pins": pins,
        "transport_status": status,
        "complete": complete,
        "schema_valid": valid,
        "model_calls": calls,
        "tokens": tokens,
        "timings": times,
        "review": review_value(
            descriptor.get("review"),
            receipt_ref["sha256"],
            roots,
            not_run=calls == 0 and not replayed,
        ),
        "holds": sorted(set(x for doc in docs for x in doc["holds"])),
        "settlement": settlement_ref,
        "projection_adapter_version": VERSION,
    }
    if replay_ref:
        run["replay_of_receipt"] = replay_ref
    require(ID.fullmatch(invocation_id), "Invalid invocation identity")
    records = []
    for doc in sorted(docs, key=lambda x: x["sha256"]):
        run_id = descriptor["run_id_prefix"] + "-" + doc["sha256"][:12]
        require(ID.fullmatch(run_id), "Projected run ID exceeds safe bound")
        records.append(
            {
                "schema": "powerlex.tracker.document-run.v1",
                "record_version": "1.1",
                "run_id": run_id,
                "pipeline_run_id": descriptor["pipeline_run_id"],
                "tool": "askmill",
                **{
                    key: doc[key]
                    for key in (
                        "sha256",
                        "title",
                        "profile_id",
                        "body",
                        "original_receipt",
                        "holds",
                    )
                },
                "requirements_sha256": descriptor["requirements_sha256"],
                "media_type": "application/pdf",
                "run_mode": "historical_reconciliation",
                "recorded_at": descriptor["recorded_at"],
                "stages": {
                    "askmill": {
                        "status": stage_status,
                        "version": version,
                        "receipt": receipt_ref,
                        "timing": {
                            "started_at": None,
                            "finished_at": None,
                            "wall_seconds": None,
                            "basis": "not_recorded",
                            "reason": "Retained invocation wall interval not established; native timings remain separate.",
                        },
                        "runs": [run],
                    }
                },
                "gold": {"kind": "none"},
                "supersedes": [],
            }
        )
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptor", type=Path, required=True)
    parser.add_argument("--descriptor-sha256", required=True)
    parser.add_argument("--evidence-root", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "Output directory must be new")
    raw = read_bytes(args.descriptor)
    require(
        sha(raw) == args.descriptor_sha256, "Projection descriptor byte pin mismatch"
    )
    roots = {}
    for pair in args.evidence_root:
        name, path = pair.split("=", 1)
        require(
            ID.fullmatch(name) and name not in roots,
            "Unique authorized repository roots required",
        )
        roots[name] = path
    args.output.mkdir(parents=True)
    try:
        records = project(loads(raw), roots)
    except (ValueError, KeyError, TypeError, IndexError, OSError) as error:
        report = {
            "schema_version": "askmill.tracker-projection-refusal.v1",
            "descriptor_sha256": sha(raw),
            "status": "refused",
            "reason": str(error),
            "new_inference": False,
            "historical_model_calls": None,
            "records_emitted": 0,
            "source_or_domain_acceptance": False,
            "adapter_version": VERSION,
        }
        (args.output / "refusal.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report))
        return 2
    data = b"".join(canonical(row) + b"\n" for row in records)
    (args.output / "runs.ndjson").write_bytes(data)
    report = {
        "schema_version": "askmill.tracker-projection-result.v1",
        "adapter_version": VERSION,
        "descriptor_sha256": sha(raw),
        "outbox_sha256": sha(data),
        "records_emitted": len(records),
        "unique_retained_invocation_ids": sorted(
            {r["stages"]["askmill"]["runs"][0]["invocation_id"] for r in records}
        ),
        "new_inference": False,
        "Map_intake_validation": "required",
        "source_or_domain_acceptance": False,
    }
    (args.output / "projection.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
