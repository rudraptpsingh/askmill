"""Small versioned JSON CLI; no PDF parsing or domain decisions."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .contract import Batch, Request
from .jsonio import MAX_BATCH_BYTES, load as load_json, read_bytes
from .profiles import from_pdf2data, load, model_revision
from .runner import Session, run_batch
from .transport import validate


def execute(args):
    if args.command == "import-pdf2data":
        data = load_json(args.config)
        if data.get("schema_version") != "pdf2data.local-models.v1":
            raise ValueError("Unsupported PDF2Data profile format")
        old = data["models"][args.profile]
        converted = from_pdf2data(old, model_revision(old["model_path"]))
        return {
            "schema_version": "askmill.profiles.v1",
            "profiles": {args.profile: converted.model_dump(exclude_none=True)},
        }
    if args.command == "mcp":
        from .mcp import serve

        serve(args.config, args.store, args.lease)
        return None
    if args.command == "list":
        return load_json(args.config)
    if args.command == "embed":
        from .embedding import FilePin, run_embedding, sha, verify_file

        registry = load_json(args.config)
        entry = registry["embedding_profiles"][args.profile]
        ref = FilePin.model_validate(entry)
        entry_sha = sha(
            json.dumps(
                entry,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        )
        verify_file(ref)
        profile_raw = read_bytes(ref.path)
        request_raw = read_bytes(args.request)
        return run_embedding(
            profile_raw,
            ref.sha256,
            request_raw,
            args.request_sha256,
            args.output,
            args.lease,
            entry_sha,
        )
    profile = load(args.config, args.profile)
    if args.command == "read-fields":
        from .pdf2data_fields import read_fields

        return read_fields(
            profile,
            args.request,
            args.output,
            args.store,
            args.lease,
            args.max_tokens,
            args.timeout,
            prompt=args.prompt,
        )
    if args.command == "doctor":
        validate(profile.model_dump(exclude_none=True))
        return {
            "status": "configuration_valid",
            "runner_version": __version__,
            "provider": profile.provider,
            "model": profile.model,
            "inference_tested": False,
        }
    if args.command == "digest":
        from .digest import digest, digest_codex_sessions

        def save_partial(reports):
            if args.output:
                partial = {"schema_version": "askmill.codex-digest.v1", "status": "partial", "sessions": reports,
                           "domain_acceptance": "unverified"}
                Path(args.output).write_text(json.dumps(partial, ensure_ascii=False, indent=2) + "\n")

        with Session(profile, args.store, args.lease) as session:
            if args.codex:
                value = digest_codex_sessions(
                    session, args.codex, focus=args.focus, tail_chars=args.tail_chars,
                    chunk_chars=args.chunk_chars, max_tokens=args.max_tokens, timeout=args.timeout,
                    on_session=save_partial,
                )
            else:
                value = digest(
                    session, read_bytes(args.input).decode("utf-8"), focus=args.focus,
                    chunk_chars=args.chunk_chars, max_tokens=args.max_tokens, timeout=args.timeout,
                )
        if args.output:
            Path(args.output).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        return value
    if args.command == "batch":
        return run_batch(
            profile,
            Batch.model_validate(load_json(args.request, MAX_BATCH_BYTES)),
            args.store,
            args.lease,
        )
    if args.request:
        request = Request.model_validate(load_json(args.request))
    else:
        request = Request(
            prompt=read_bytes(args.input).decode("utf-8"),
            images=args.image,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
        )
    with Session(profile, args.store, args.lease) as session:
        return session.run(request).model_dump()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version="askmill " + __version__)
    parser.add_argument(
        "--config", default=str(Path.home() / ".config/askmill/profiles.json")
    )
    parser.add_argument(
        "--store", default=str(Path.home() / ".local/state/askmill/receipts")
    )
    parser.add_argument(
        "--lease", action="append", help="Repeat for existing host GPU locks"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    for command in ("doctor", "import-pdf2data"):
        child = sub.add_parser(command)
        child.add_argument("--profile", required=True)
    run = sub.add_parser("run")
    run.add_argument("--profile", required=True)
    inputs = run.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--input")
    inputs.add_argument("--request")
    run.add_argument("--image", action="append", default=[])
    run.add_argument("--max-tokens", type=int, default=2048)
    run.add_argument("--timeout", type=float, default=180.0)
    embed = sub.add_parser(
        "embed", help="Run one explicitly registered embedding batch"
    )
    embed.add_argument("--profile", required=True)
    embed.add_argument("--request", required=True)
    embed.add_argument("--request-sha256", required=True)
    embed.add_argument("--output", required=True)
    dig = sub.add_parser(
        "digest", help="Summarize long text or Codex session transcripts in chunks, then merge"
    )
    dig.add_argument("--profile", required=True)
    source = dig.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", help="UTF-8 text file")
    source.add_argument("--codex", nargs="+", help="Codex rollout .jsonl session files")
    dig.add_argument("--focus", default="progress, decisions, open issues and next steps")
    dig.add_argument("--tail-chars", type=int, default=60000, help="Codex: keep the first ask and this much of the latest conversation")
    dig.add_argument("--chunk-chars", type=int, default=14000)
    dig.add_argument("--max-tokens", type=int, default=900)
    dig.add_argument("--timeout", type=float, default=600.0)
    dig.add_argument("--output", help="Also write the JSON result to this file")
    batch = sub.add_parser("batch")
    batch.add_argument("--profile", required=True)
    batch.add_argument("--request", required=True, help="JSON Batch contract file")
    fields = sub.add_parser("read-fields")
    fields.add_argument("--profile", required=True)
    fields.add_argument(
        "--request",
        required=True,
        help="Verified PDF2Data field witness request bundle",
    )
    fields.add_argument("--output", required=True)
    fields.add_argument(
        "--prompt",
        help="Explicit specialist transcription prompt; retained with the reading",
    )
    fields.add_argument("--max-tokens", type=int, default=2048)
    fields.add_argument("--timeout", type=float, default=180.0)
    sub.add_parser("mcp")
    args = parser.parse_args()
    try:
        if not args.lease:
            config = Path(args.config)
            data = load_json(config) if config.exists() else {}
            leases = data.get(
                "lease_paths", [str(Path.home() / ".local/state/askmill/gpu.lock")]
            )
            if (
                not isinstance(leases, list)
                or not 1 <= len(leases) <= 8
                or any(
                    not isinstance(p, str) or not Path(p).is_absolute() for p in leases
                )
            ):
                raise ValueError("lease_paths must contain 1..8 absolute paths")
            args.lease = leases
        value = execute(args)
        if value is not None:
            print(json.dumps(value, ensure_ascii=False))
        if value and value.get("status") == "schema_invalid":
            return 4
        return 3 if value and value.get("status") == "incomplete" else 0
    except (Exception, KeyboardInterrupt) as error:
        print(
            json.dumps(
                {
                    "status": "cancelled"
                    if isinstance(error, KeyboardInterrupt)
                    else getattr(error, "status", "invalid_or_unavailable"),
                    "error": str(error),
                }
            )
        )
        return 130 if isinstance(error, KeyboardInterrupt) else 2


if __name__ == "__main__":
    sys.exit(main())
