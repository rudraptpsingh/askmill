"""Small versioned JSON CLI; no PDF parsing or domain decisions."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .contract import Batch, Request
from .profiles import from_pdf2data, load, model_revision
from .runner import Session, run_batch
from .transport import validate


def execute(args):
    if args.command == "import-pdf2data":
        data = json.loads(Path(args.config).read_text())
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
        return json.loads(Path(args.config).read_text())
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
    if args.command == "batch":
        return run_batch(
            profile,
            Batch.model_validate_json(Path(args.request).read_text()),
            args.store,
            args.lease,
        )
    if args.request:
        request = Request.model_validate_json(Path(args.request).read_text())
    else:
        request = Request(
            prompt=Path(args.input).read_text(),
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
            data = json.loads(config.read_text()) if config.exists() else {}
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
