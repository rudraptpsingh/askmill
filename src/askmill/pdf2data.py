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
            "askmill_receipt_id": result.receipt_id,
            "replayed": result.replayed,
        }

    def close(self):
        self._session.close()
        self._opened = False
