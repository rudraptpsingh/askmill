"""Scoped worker lifecycle and content-addressed per-item receipts (POSIX v0)."""

import base64
import fcntl
import hashlib
import json
import os
import selectors
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from .contract import Profile, Request, Result
from .transport import request as http_request
from .transport import validate

LIMIT = 16 * 1024 * 1024


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class RunError(RuntimeError):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


class Session:
    """All callers on a host must use the SAME lease path. Store is workspace-scoped."""

    def __init__(self, profile: Profile, store, lease):
        self.profile = profile
        self.store = Path(store)
        self.store.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lease_paths = sorted(
            {
                Path(p).absolute()
                for p in (lease if isinstance(lease, (list, tuple)) else [lease])
            }
        )
        if not self.lease_paths:
            raise ValueError("At least one device lease is required")
        self.quarantines = [Path(str(p) + ".unsettled") for p in self.lease_paths]
        self.quarantine = self.quarantines[0]
        self.locks = []
        self.worker = None
        self.session_id = None
        self.settlement = None
        self.external_request_settlement = "not_sent"
        self.stderr = None
        self.buffer = b""
        self.runtime = {
            "transport_sha256": hashlib.sha256(
                Path(__file__).with_name("transport.py").read_bytes()
            ).hexdigest()
        }

    def __enter__(self):
        self.session_id = str(uuid.uuid4())
        self.settlement = None
        self.external_request_settlement = "not_sent"
        if any(p.exists() for p in self.quarantines):
            raise RunError(
                "cleanup_uncertain",
                "Verify external generation stopped before clearing lease.unsettled",
            )
        try:
            for path in self.lease_paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                lock = path.open("a+b")
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    lock.close()
                    raise RunError("busy", "Device lease is held") from None
                self.locks.append(lock)
            if any(p.exists() for p in self.quarantines):
                raise RunError("cleanup_uncertain", "Device is quarantined")
            validate(self.profile.model_dump(exclude_none=True))
            if self.profile.provider == "ollama":
                self._verify_ollama()
            if self.profile.provider == "mlx-vlm":
                from .profiles import model_revision

                if model_revision(self.profile.model_path) != self.profile.revision:
                    raise RunError(
                        "model_mismatch", "Cached MLX bytes differ from profile"
                    )
            if self.profile.provider == "openai-compatible":
                raise RunError(
                    "unsupported",
                    "Exact model identity attestation is not implemented for this provider",
                )
            executable = (
                self.profile.python
                if self.profile.provider == "mlx-vlm"
                else sys.executable
            )
            env = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
            self.stderr = tempfile.TemporaryFile()
            self.worker = subprocess.Popen(
                [executable, str(Path(__file__).with_name("worker.py"))],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self.stderr,
                env=env,
                start_new_session=True,
                pass_fds=tuple(lock.fileno() for lock in self.locks),
            )
            ready = self._exchange(
                {
                    "op": "open",
                    "profile": self.profile.model_dump(exclude_none=True),
                    "quarantine_paths": [str(p) for p in self.quarantines],
                },
                15,
            )
            self.runtime.update(ready["runtime"])
            return self
        except BaseException:
            self.close()
            raise

    def _verify_ollama(self):
        version = http_request(
            self.profile.model_dump(), "api/version", timeout=10
        ).get("version")
        if not isinstance(version, str) or not version:
            raise RunError("runtime_unavailable", "Ollama version unavailable")
        if self.runtime.get("ollama_version", version) != version:
            raise RunError(
                "runtime_mismatch", "Ollama runtime changed during the session"
            )
        self.runtime["ollama_version"] = version
        details = http_request(
            self.profile.model_dump(),
            "api/show",
            {"model": self.profile.model},
            timeout=10,
        )
        if (
            details.get("remote_host")
            or details.get("remote_model")
            or "cloud" in self.profile.model.lower()
        ):
            raise RunError(
                "unsupported", "Cloud-backed Ollama models are not local profiles"
            )
        if self.profile.generation:
            selected = self.profile.generation.thinking
            controls = details.get("thinking", {})
            values = controls.get("values")
            if (
                selected is not None
                and values is not None
                and not any(
                    type(selected) is type(value) and selected == value
                    for value in values
                )
            ):
                raise RunError(
                    "unsupported",
                    "Selected thinking control is unsupported by this model",
                )
            if selected is None:
                self.runtime["ollama_default_thinking"] = json.dumps(
                    controls.get("default")
                )
        capabilities = details.get("capabilities", [])
        if any(
            ("completion" if capability == "text" else capability) not in capabilities
            for capability in self.profile.capabilities
        ):
            raise RunError(
                "unsupported",
                "Installed model does not provide the profile capabilities",
            )
        tags = http_request(self.profile.model_dump(), "api/tags", timeout=10)
        actual = next(
            (
                m.get("digest")
                for m in tags.get("models", [])
                if m.get("name") == self.profile.model
            ),
            None,
        )
        if actual != self.profile.revision:
            raise RunError(
                "model_mismatch", "Installed Ollama tag/digest differs from profile"
            )

    def _exchange(self, message, timeout):
        self.worker.stdin.write(json.dumps(message).encode() + b"\n")
        self.worker.stdin.flush()
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            selector.register(self.worker.stdout, selectors.EVENT_READ)
            while b"\n" not in self.buffer:
                wait = deadline - time.monotonic()
                if wait <= 0 or not selector.select(wait):
                    raise RunError("timeout", "Inference deadline exceeded")
                chunk = os.read(self.worker.stdout.fileno(), 65536)
                if not chunk:
                    raise RunError("worker_failed", "Worker exited without a response")
                self.buffer += chunk
                if len(self.buffer) > LIMIT:
                    raise RunError("output_limit", "Worker response exceeded limit")
        line, self.buffer = self.buffer.split(b"\n", 1)
        data = json.loads(line)
        if "error" in data:
            raise RunError("provider_error", data["error"])
        return data.get("ok", data)

    def run(self, request: Request):
        if not self.worker or self.worker.poll() is not None:
            raise RunError("closed", "Open a session before inference")
        needed = "vision" if request.images else "text"
        if needed not in self.profile.capabilities:
            raise RunError("unsupported", "Profile does not support " + needed)
        # Freeze actual bytes, not just paths, before handing anything to the model.
        snapshot = request.model_dump()
        frozen = []
        for name in request.images:
            path = Path(name)
            if path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
                raise RunError("unsupported", "Use PNG, JPEG or WebP crops")
            with path.open("rb") as handle:
                raw = handle.read(LIMIT + 1)
            if len(raw) > LIMIT:
                raise RunError("input_limit", "Image exceeds 16 MiB")
            frozen.append(
                {
                    "extension": path.suffix.lower(),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "base64": base64.b64encode(raw).decode(),
                }
            )
        snapshot["images"] = frozen
        key = digest(
            {
                "request": snapshot,
                "profile": self.profile.model_dump(),
                "runtime": self.runtime,
            }
        )
        target = self.store / (key + ".json")
        if target.exists():
            record = json.loads(target.read_text())
            content = record["content"]
            if digest(content) != record["sha256"] or content["key"] != key:
                raise RunError("receipt_corrupt", "Receipt integrity check failed")
            if (
                content["request"] != snapshot
                or content["profile"] != self.profile.model_dump()
                or content["runtime"] != self.runtime
            ):
                raise RunError("receipt_corrupt", "Receipt inputs differ")
            return Result.model_validate(content["result"]).model_copy(
                update={"replayed": True}
            )
        attempt = str(uuid.uuid4())
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="askmill-") as folder:
            paths = []
            for i, image in enumerate(frozen):
                path = Path(folder) / (str(i) + image["extension"])
                path.write_bytes(base64.b64decode(image["base64"]))
                paths.append(str(path))
            try:
                if self.profile.ownership == "external":
                    self.external_request_settlement = "pending"
                raw = self._exchange(
                    {
                        "op": "generate",
                        "args": {
                            "prompt": request.prompt,
                            "images": paths,
                            "max_tokens": request.max_tokens,
                            "timeout": request.timeout,
                        },
                    },
                    request.timeout,
                )
                if self.profile.provider == "ollama":
                    if raw.get("raw_response", {}).get("done") is not True:
                        raise RunError(
                            "cleanup_uncertain",
                            "External server did not acknowledge generation termination",
                        )
                    self.external_request_settlement = "acknowledged"
                    self._verify_ollama()
                if raw["model"] != self.profile.model:
                    raise RunError(
                        "model_mismatch", "Response model differs from profile"
                    )
            except BaseException:
                # HTTP disconnect is NOT proof the server stopped computing.
                if self.profile.ownership == "external":
                    if self.external_request_settlement == "pending":
                        self.external_request_settlement = "unconfirmed"
                    for marker in self.quarantines:
                        marker.write_text(
                            json.dumps(
                                {
                                    "attempt_id": attempt,
                                    "reason": "external settlement unconfirmed",
                                }
                            )
                        )
                self.close()
                raise
        result = Result(
            status="completed" if raw["complete"] else "incomplete",
            text=raw["text"],
            complete=raw["complete"],
            model=raw["model"],
            revision=self.profile.revision,
            generated_tokens=raw.get("generated_tokens"),
            seconds=time.monotonic() - started,
            runtime=dict(self.runtime),
            device=raw.get("device"),
            peak_device_memory_bytes=raw.get("peak_device_memory_bytes"),
            receipt_id=key,
            attempt_id=attempt,
            session_id=self.session_id,
        )
        content = {
            "key": key,
            "request": snapshot,
            "profile": self.profile.model_dump(),
            "result": result.model_dump(),
            "runtime": dict(self.runtime),
        }
        fd, name = tempfile.mkstemp(dir=self.store, prefix=".attempt-")
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump({"content": content, "sha256": digest(content)}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, target)
            directory = os.open(self.store, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        return result

    def close(self):
        if self.settlement is not None:
            return self.settlement
        worker = self.worker
        lock_count = len(self.locks)
        try:
            if self.worker:
                if self.worker.poll() is None:
                    try:
                        self._exchange({"op": "close"}, 2)
                        self.worker.wait(timeout=2)
                    except (Exception, KeyboardInterrupt):
                        if self.worker.poll() is None:
                            try:
                                os.killpg(self.worker.pid, signal.SIGKILL)
                            except (ProcessLookupError, PermissionError):
                                if self.worker.poll() is None:
                                    self.quarantine.write_text(
                                        "Owned worker cleanup unconfirmed"
                                    )
                                    raise RunError(
                                        "cleanup_uncertain",
                                        "Unable to stop owned worker",
                                    )
                        self.worker.wait()
                for stream in (self.worker.stdin, self.worker.stdout):
                    stream.close()
                self.worker = None
        finally:
            if self.stderr:
                self.stderr.close()
                self.stderr = None
            for lock in reversed(self.locks):
                # Closing our FD preserves a worker-inherited lease if cleanup failed.
                lock.close()
            self.locks.clear()
            if worker is not None:
                content = {
                    "schema_version": "askmill.settlement.v1",
                    "session_id": self.session_id,
                    "worker_pid": worker.pid,
                    "worker_reaped": worker.poll() is not None,
                    "ownership": self.profile.ownership,
                    "external_service_stopped": False,
                    "external_request_settlement": self.external_request_settlement,
                    "lease_handles_closed": lock_count,
                    "quarantined": any(p.exists() for p in self.quarantines),
                }
                folder = self.store / "settlements"
                folder.mkdir(exist_ok=True, mode=0o700)
                target = folder / (self.session_id + ".json")
                fd, name = tempfile.mkstemp(dir=folder, prefix=".settlement-")
                try:
                    with os.fdopen(fd, "w") as handle:
                        json.dump(
                            {"content": content, "sha256": digest(content)}, handle
                        )
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(name, target)
                    directory = os.open(folder, os.O_RDONLY)
                    try:
                        os.fsync(directory)
                    finally:
                        os.close(directory)
                finally:
                    if os.path.exists(name):
                        os.unlink(name)
                self.settlement = content
        return self.settlement

    def __exit__(self, *args):
        self.close()


def run_batch(profile, batch, store, lease):
    """Return results in caller order in one bounded warm session."""
    with Session(profile, store, lease) as session:
        results = [session.run(request).model_dump() for request in batch.requests]
    return {
        "status": "completed" if all(r["complete"] for r in results) else "incomplete",
        "results": results,
    }
