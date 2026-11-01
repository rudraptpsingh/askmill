"""Persistent stdlib-only worker, also usable from an existing MLX venv."""

import contextlib
import json
import importlib.metadata
import platform
from pathlib import Path
import sys
import traceback

# Direct execution intentionally avoids importing the pydantic-based package.
from transport import Session
from jsonio import loads as load_json_bytes, MAX_BATCH_BYTES

session = None
quarantine_paths = []
try:
    for line in iter(lambda: sys.stdin.buffer.readline(MAX_BATCH_BYTES + 1), b""):
        data = {}
        try:
            data = load_json_bytes(line, MAX_BATCH_BYTES)
            with contextlib.redirect_stdout(sys.stderr):
                if data["op"] == "open":
                    session = Session(data["profile"])
                    quarantine_paths = data.get("quarantine_paths", [])
                    runtime = {"python": platform.python_version()}
                    for package in (
                        "mlx",
                        "mlx-vlm",
                        "transformers",
                        "pillow",
                        "tokenizers",
                    ):
                        try:
                            runtime[package] = importlib.metadata.version(package)
                        except importlib.metadata.PackageNotFoundError:
                            runtime[package] = "not-installed"
                    result = {"ready": True, "runtime": runtime}
                elif data["op"] == "generate":
                    result = session.generate(**data["args"])
                elif data["op"] == "close":
                    if session:
                        session.close()
                    result = {"closed": True}
                else:
                    raise ValueError("Unknown worker operation")
            print(json.dumps({"ok": result}), flush=True)
            if data["op"] == "close":
                break
        except Exception as error:
            if (
                session
                and data.get("op") == "generate"
                and session.profile["provider"] != "mlx-vlm"
            ):
                for path in quarantine_paths:
                    Path(path).write_text(
                        json.dumps(
                            {"reason": "worker: external settlement unconfirmed"}
                        )
                    )
            traceback.print_exc(file=sys.stderr)
            print(json.dumps({"error": str(error)}), flush=True)
finally:
    if session:
        session.close()
