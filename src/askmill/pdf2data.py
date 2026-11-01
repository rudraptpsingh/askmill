"""Opt-in compatibility shim for PDF2Data's MLX Session boundary.

The consumer retains crops, request/response files, exit codes and review state.
This module never reads or rewrites PDF2Data configuration.
"""

from .contract import Request
from .profiles import from_pdf2data, model_revision
from .runner import Session


class MLXSession:
    def __init__(self, profile, *, store, lease):
        converted = from_pdf2data(profile, model_revision(profile["model_path"]))
        self._session = Session(converted, store, lease)
        self._opened = False

    def generate(self, prompt, images=(), max_tokens=2048, timeout=180):
        if not self._opened:
            self._session.__enter__()
            self._opened = True
        result = self._session.run(
            Request(
                prompt=prompt,
                images=[str(p) for p in images],
                max_tokens=max_tokens,
                timeout=float(timeout),
            )
        )
        return {
            "text": result.text,
            "generated_tokens": result.generated_tokens,
            "complete": result.complete,
            "seconds": result.seconds,
            "model": result.model,
            "device": result.device,
            "peak_device_memory_bytes": result.peak_device_memory_bytes,
            "askmill_receipt_id": result.receipt_id,
            "replayed": result.replayed,
        }

    def close(self):
        self._session.close()
        self._opened = False


def main(argv=None):
    """Explicit bridge to a compatible installed PDF2Data, preserving its CLI."""
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Route PDF2Data MLX calls through AskMill; pass PDF2Data arguments after --."
    )
    parser.add_argument("--store", required=True)
    parser.add_argument("--lease", action="append", required=True)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    arguments = args.arguments
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    if not arguments:
        parser.error("Supply a PDF2Data command after --")
    try:
        from local_vector_batch import local_ai, cli
    except ImportError:
        print(
            json.dumps(
                {
                    "status": "unsupported_consumer",
                    "error": "Install a PDF2Data revision with local_ai named profiles; see docs/pdf2data.md",
                }
            )
        )
        return 2
    original = local_ai.Session

    def factory(profile):
        if profile["provider"] == "mlx-vlm":
            return MLXSession(profile, store=args.store, lease=args.lease)
        return original(profile)

    local_ai.Session = factory
    try:
        return cli.main(arguments)
    finally:
        local_ai.Session = original


if __name__ == "__main__":
    import sys

    sys.exit(main())
