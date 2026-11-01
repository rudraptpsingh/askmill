"""Persistent stdlib-only worker, also usable from an existing MLX venv."""

import contextlib
import json
import sys
import traceback

# Direct execution intentionally avoids importing the pydantic-based package.
from transport import Session

session = None
try:
    for line in sys.stdin:
        try:
            data = json.loads(line)
            with contextlib.redirect_stdout(sys.stderr):
                if data["op"] == "open":
                    session = Session(data["profile"])
                    result = {"ready": True}
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
            traceback.print_exc(file=sys.stderr)
            print(json.dumps({"error": str(error)}), flush=True)
finally:
    if session:
        session.close()
