"""Explicit local Ollama embedding batches with host-owned context authority."""

import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import socket
import struct
import threading
import subprocess
import time
import urllib.request
import uuid

from pydantic import Field, field_validator, model_validator

from .contract import Strict
from .jsonio import load


class FilePin(Strict):
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("path")
    @classmethod
    def absolute(cls, value):
        if not Path(value).is_absolute():
            raise ValueError("Pin paths must be absolute")
        return value


class EmbeddingProfile(Strict):
    schema_version: str = "askmill.embedding-profile.v1"
    provider: str = "ollama-owned"
    capabilities: list[str] = ["embedding"]
    model: str = Field(min_length=1, max_length=300)
    model_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    dimensions: int = Field(ge=1, le=65536)
    context_tokens: int = Field(ge=1, le=131072)
    tokenizer: FilePin
    tokenizers_version: str = Field(min_length=1)
    psutil_version: str = Field(min_length=1)
    model_manifest: FilePin
    model_store: str
    provider_binary: FilePin
    runtime_files: list[FilePin] = Field(min_length=1, max_length=256)
    provider_version: str = Field(min_length=1)
    context_gate: FilePin
    lease_paths: list[str] = Field(min_length=1, max_length=8)
    min_available_bytes: int = Field(ge=1)
    max_owned_rss_bytes: int = Field(ge=1)
    timeout_seconds: int = Field(ge=1, le=3600)

    @model_validator(mode="after")
    def valid_profile(self):
        if (
            self.schema_version != "askmill.embedding-profile.v1"
            or self.provider != "ollama-owned"
            or self.capabilities != ["embedding"]
        ):
            raise ValueError("Unsupported embedding profile")
        if (
            not Path(self.model_store).is_absolute()
            or any(not Path(p).is_absolute() for p in self.lease_paths)
            or len(set(self.lease_paths)) != len(self.lease_paths)
        ):
            raise ValueError("Require absolute store and distinct lease paths")
        if self.model_manifest.sha256 != self.model_revision:
            raise ValueError("Model manifest and revision must match")
        return self


class EmbeddingItem(Strict):
    id: str = Field(min_length=1, max_length=512)
    text: str = Field(min_length=1, max_length=64000)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def checked(self):
        if hashlib.sha256(self.text.encode()).hexdigest() != self.sha256:
            raise ValueError("Input text hash differs")
        return self


class EmbeddingRequest(Strict):
    schema_version: str = "askmill.embedding-batch.v1"
    batch_id: str = Field(min_length=1, max_length=512)
    scope_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    items: list[EmbeddingItem] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def checked(self):
        if self.schema_version != "askmill.embedding-batch.v1" or len(
            {x.id for x in self.items}
        ) != len(self.items):
            raise ValueError("Unsupported request or duplicate IDs")
        return self


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def verify_file(pin):
    digest = hashlib.sha256()
    with Path(pin.path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != pin.sha256:
        raise ValueError("Pinned file differs: " + pin.path)


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(
            value, stream, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2
        )
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def write_bytes_new(path, data):
    with Path(path).open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def verify_model(profile):
    for pin in [
        profile.provider_binary,
        profile.model_manifest,
        profile.tokenizer,
        *profile.runtime_files,
    ]:
        verify_file(pin)
    manifest = load(profile.model_manifest.path)
    layers = [manifest["config"], *manifest["layers"]]
    if not any(
        x.get("name") == "tokenizer.json"
        and x.get("digest") == "sha256:" + profile.tokenizer.sha256
        for x in layers
    ):
        raise ValueError("Tokenizer is not bound to the model manifest")
    for item in layers:
        value = item.get("digest", "")
        if not value.startswith("sha256:") or len(value) != 71:
            raise ValueError("Invalid model layer digest")
        blob = Path(profile.model_store) / "blobs" / value.replace(":", "-", 1)
        if blob.stat().st_size != item["size"]:
            raise ValueError("Model layer size differs")
        verify_file(FilePin(path=str(blob), sha256=value[7:]))


def http(endpoint, path, data=None, timeout=10):
    body = None if data is None else json.dumps(data, allow_nan=False).encode()
    req = urllib.request.Request(
        endpoint + path, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        req, timeout=timeout
    ) as response:
        raw = response.read(64 * 1024 * 1024 + 1)
    if len(raw) > 64 * 1024 * 1024:
        raise ValueError("Provider response too large")
    return json.loads(raw)


def _stop_owned(process, psutil, known):
    # Only observed descendants with unchanged PID/create-time can be signalled.
    try:
        parent = psutil.Process(process.pid)
        for child in parent.children(recursive=True):
            known.setdefault(child.pid, child.create_time())
    except psutil.NoSuchProcess:
        pass
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
    remaining = []
    for pid, created in known.items():
        try:
            child = psutil.Process(pid)
            if child.create_time() != created:
                raise ValueError("Observed child PID identity changed")
            if child.status() != psutil.STATUS_ZOMBIE:
                child.terminate()
                remaining.append(child)
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(remaining, timeout=2)
    for child in alive:
        if child.create_time() != known[child.pid]:
            raise ValueError("Observed child PID identity changed")
        child.kill()
    _, alive = psutil.wait_procs(alive, timeout=2)
    try:
        os.killpg(process.pid, 0)
        group_alive = True
    except ProcessLookupError:
        group_alive = False
    return not alive and not group_alive


def run_embedding(
    profile_raw,
    profile_sha256,
    request_raw,
    request_sha256,
    output,
    expected_leases=None,
    registry_entry_sha256=None,
):
    """Run exactly one explicitly authorized data batch; no retries/fallback.

    Context-gate code is trusted host configuration and must authenticate its
    opaque scope, budget reservation and current authority on both checks.
    """
    import tokenizers
    import psutil

    if sha(profile_raw) != profile_sha256 or sha(request_raw) != request_sha256:
        raise ValueError("Frozen profile or request hash differs")
    profile = EmbeddingProfile.model_validate_json(profile_raw)
    request = EmbeddingRequest.model_validate_json(request_raw)
    if expected_leases is not None and list(expected_leases) != profile.lease_paths:
        raise ValueError("CLI and embedding profile lease paths differ")
    if (
        tokenizers.__version__ != profile.tokenizers_version
        or psutil.__version__ != profile.psutil_version
    ):
        raise ValueError("Tokenizer or resource runtime version differs from profile")
    verify_file(profile.context_gate)
    spec = importlib.util.spec_from_file_location(
        "askmill_embedding_context_gate", profile.context_gate.path
    )
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    if gate.authorize(profile.model_dump(), request.model_dump(), "before") is not True:
        raise ValueError("Current context gate refused")
    verify_model(profile)
    tokenizer = tokenizers.Tokenizer.from_file(profile.tokenizer.path)
    tokenizer.no_truncation()
    token_counts = [
        len(tokenizer.encode(item.text, add_special_tokens=True).ids)
        for item in request.items
    ]
    if any(count <= 0 or count > profile.context_tokens for count in token_counts):
        raise ValueError("Input exceeds tokenizer context; no truncation")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    write_bytes_new(output / "request.json", request_raw)
    write_bytes_new(output / "profile.json", profile_raw)
    leases = []
    attempt_markers = []
    marker_content = {
        "schema_version": "askmill.embedding-active-attempt.v1",
        "attempt_id": str(uuid.uuid4()),
        "request_sha256": request_sha256,
    }
    process = None
    data_started = False
    data_ack = False
    cleanup_ack = False
    cleanup_started = False
    unload_verified = False
    worker_settled = True
    result = None
    reservation = None
    error = None
    started = time.monotonic()
    monitor_stop = threading.Event()
    monitor = None
    known_children = {}
    lease_identities = []
    monitor_state = {
        "violation": None,
        "sample_count": 0,
        "peak_owned_rss_bytes": 0,
        "minimum_available_bytes": None,
    }
    try:
        for name in profile.lease_paths:
            marker = Path(name + ".unsettled")
            if marker.exists():
                raise ValueError("Shared lease is quarantined")
            fd = os.open(name, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
            handle = os.fdopen(fd, "r+")
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                st, current = os.fstat(handle.fileno()), Path(name).stat()
                if (st.st_dev, st.st_ino) != (current.st_dev, current.st_ino):
                    raise ValueError("Shared lease identity changed")
            except BaseException:
                handle.close()
                raise
            leases.append(handle)
            lease_identities.append(
                {"path": name, "device": st.st_dev, "inode": st.st_ino}
            )
        if any(Path(name + ".unsettled").exists() for name in profile.lease_paths):
            raise ValueError("Shared lease is quarantined")
        if psutil.virtual_memory().available < profile.min_available_bytes:
            raise ValueError("Insufficient available memory")
        reservation = gate.reserve(
            profile.model_dump(), request.model_dump(), request_sha256
        )
        if not isinstance(reservation, str) or not reservation:
            raise ValueError("Context gate did not reserve budget")
        write_new(
            output / "reservation.json",
            {
                "request_sha256": request_sha256,
                "profile_sha256": profile_sha256,
                "reservation": reservation,
                "state": "reserved_no_retry",
            },
        )
        # Mark every leased device before starting an owned service. A parent
        # crash leaves these markers behind, even if inherited locks disappear.
        for name in profile.lease_paths:
            marker = Path(name + ".unsettled")
            write_new(marker, marker_content)
            attempt_markers.append(marker)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        endpoint = "http://127.0.0.1:" + str(port)
        env = dict(os.environ)
        env.update(
            {
                "OLLAMA_HOST": "127.0.0.1:" + str(port),
                "OLLAMA_MODELS": profile.model_store,
                "OLLAMA_NO_CLOUD": "1",
                "OLLAMA_NUM_PARALLEL": "1",
                "OLLAMA_MAX_LOADED_MODELS": "1",
                "OLLAMA_CONTEXT_LENGTH": str(profile.context_tokens),
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
            }
        )
        with (output / "provider.log").open("xb") as log:
            process = subprocess.Popen(
                [profile.provider_binary.path, "serve"],
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                pass_fds=tuple(handle.fileno() for handle in leases),
            )
            parent_process = psutil.Process(process.pid)
            identity = parent_process.create_time()
            initial_rss = parent_process.memory_info().rss
            initial_available = psutil.virtual_memory().available
            monitor_state.update(
                {
                    "sample_count": 1,
                    "peak_owned_rss_bytes": initial_rss,
                    "minimum_available_bytes": initial_available,
                }
            )
            if (
                initial_available < profile.min_available_bytes
                or initial_rss > profile.max_owned_rss_bytes
            ):
                raise ValueError("Embedding resource start limits exceeded")

            def monitor_resources():
                while not monitor_stop.wait(0.2):
                    try:
                        parent = psutil.Process(process.pid)
                        if parent.create_time() != identity:
                            raise ValueError("Owned process identity changed")
                        children = parent.children(recursive=True)
                        for child in children:
                            known_children.setdefault(child.pid, child.create_time())
                        processes = [parent, *children]
                        rss = sum(
                            p.memory_info().rss for p in processes if p.is_running()
                        )
                        available = psutil.virtual_memory().available
                        monitor_state["sample_count"] += 1
                        monitor_state["peak_owned_rss_bytes"] = max(
                            monitor_state["peak_owned_rss_bytes"], rss
                        )
                        old = monitor_state["minimum_available_bytes"]
                        monitor_state["minimum_available_bytes"] = (
                            available if old is None else min(old, available)
                        )
                        if (
                            available < profile.min_available_bytes
                            or rss > profile.max_owned_rss_bytes
                        ):
                            raise ValueError("Embedding resource limit exceeded")
                    except BaseException as exc:
                        monitor_state["violation"] = type(exc).__name__ + ":" + str(exc)
                        if (
                            process.poll() is None
                            and os.getpgid(process.pid) == process.pid
                        ):
                            os.killpg(process.pid, signal.SIGTERM)
                        return

            monitor = threading.Thread(target=monitor_resources, daemon=True)
            monitor.start()
            for _ in range(100):
                if process.poll() is not None:
                    raise ValueError("Owned provider stopped before ready")
                try:
                    version = http(endpoint, "/api/version", timeout=1)["version"]
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                raise ValueError("Owned provider not ready")
            if version != profile.provider_version:
                raise ValueError("Provider version differs")
            listeners = subprocess.check_output(
                ["lsof", "-nP", "-t", "-iTCP:" + str(port), "-sTCP:LISTEN"], text=True
            ).splitlines()
            if listeners != [str(process.pid)]:
                raise ValueError("Provider listener is not owned")
            tags = http(endpoint, "/api/tags", timeout=5)
            matches = [
                m for m in tags.get("models", []) if m.get("name") == profile.model
            ]
            if len(matches) != 1 or matches[0].get("digest") != profile.model_revision:
                raise ValueError("Provider model revision differs")
            details = http(endpoint, "/api/show", {"model": profile.model}, timeout=5)
            if details.get("remote_host") or details.get("remote_model"):
                raise ValueError("Remote model refused")
            if "embedding" not in details.get("capabilities", []):
                raise ValueError("Selected model has no embedding capability")
            write_new(
                output / "runtime.json",
                {
                    "schema_version": "askmill.embedding-runtime.v1",
                    "provider_pid": process.pid,
                    "provider_version": version,
                    "provider_binary_sha256": profile.provider_binary.sha256,
                    "model": profile.model,
                    "model_revision": profile.model_revision,
                    "tokenizer_sha256": profile.tokenizer.sha256,
                    "tokenizers_version": profile.tokenizers_version,
                    "psutil_version": profile.psutil_version,
                    "declared_context_tokens": profile.context_tokens,
                    "runtime_files": [
                        pin.model_dump() for pin in profile.runtime_files
                    ],
                },
            )
            for pin in [
                profile.context_gate,
                profile.provider_binary,
                profile.model_manifest,
                profile.tokenizer,
                *profile.runtime_files,
            ]:
                verify_file(pin)
            if (
                gate.authorize(
                    profile.model_dump(), request.model_dump(), "before_dispatch"
                )
                is not True
            ):
                raise ValueError("Current context gate revoked before dispatch")
            if psutil.virtual_memory().available < profile.min_available_bytes:
                raise ValueError("Insufficient available memory before dispatch")
            remaining = profile.timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError("Embedding deadline elapsed")
            payload = {
                "model": profile.model,
                "input": [item.text for item in request.items],
                "dimensions": profile.dimensions,
                "truncate": False,
                "options": {"num_ctx": profile.context_tokens},
            }
            data_started = True
            response = http(endpoint, "/api/embed", payload, timeout=remaining)
            data_ack = True
            write_new(output / "provider-response.json", response)
            vectors = response.get("embeddings")
            if (
                response.get("model") != profile.model
                or type(response.get("prompt_eval_count")) is not int
                or response.get("prompt_eval_count") != sum(token_counts)
                or not isinstance(vectors, list)
                or len(vectors) != len(request.items)
            ):
                raise ValueError(
                    "Provider identity, token count or vector count differs"
                )
            rows = []
            for item, values in zip(request.items, vectors):
                if (
                    not isinstance(values, list)
                    or len(values) != profile.dimensions
                    or any(
                        type(v) not in (int, float) or not math.isfinite(v)
                        for v in values
                    )
                ):
                    raise ValueError("Invalid embedding vector")
                packed = struct.pack("<" + str(profile.dimensions) + "f", *values)
                f32 = struct.unpack("<" + str(profile.dimensions) + "f", packed)
                if (
                    any(not math.isfinite(v) for v in f32)
                    or abs(math.sqrt(sum(v * v for v in f32)) - 1) >= 0.002
                ):
                    raise ValueError("Embedding vector is not finite and normalized")
                rows.append(
                    {
                        "id": item.id,
                        "input_sha256": item.sha256,
                        "vector_sha256": sha(packed),
                        "values": list(f32),
                    }
                )
            loaded = http(endpoint, "/api/ps", timeout=5).get("models", [])
            selected = [m for m in loaded if m.get("name") == profile.model]
            if (
                len(selected) != 1
                or selected[0].get("context_length") != profile.context_tokens
            ):
                raise ValueError(
                    "Actual embedding context allocation is unknown or differs"
                )
            if monitor_state["violation"]:
                raise ValueError("Embedding resource monitor refused")
            cleanup_started = True
            cleanup = http(
                endpoint,
                "/api/embed",
                {"model": profile.model, "input": [], "keep_alive": 0},
                timeout=max(
                    1, min(15, profile.timeout_seconds - (time.monotonic() - started))
                ),
            )
            cleanup_ack = isinstance(cleanup, dict)
            unload_verified = http(endpoint, "/api/ps", timeout=5).get("models") == []
            if not cleanup_ack or not unload_verified:
                raise ValueError("Owned model unload not acknowledged")
            result = {
                "schema_version": "askmill.embedding-result.v1",
                "batch_id": request.batch_id,
                "request_sha256": request_sha256,
                "profile_sha256": profile_sha256,
                "registry_entry_sha256": registry_entry_sha256,
                "scope_sha256": request.scope_sha256,
                "dimensions": profile.dimensions,
                "rows": rows,
                "provider_data_requests": 1,
                "cleanup_requests": 1,
                "actual_input_tokens": response["prompt_eval_count"],
                "actual_context_tokens": selected[0]["context_length"],
                "silent_truncation": False,
                "domain_acceptance": "unverified",
            }
    except BaseException as exc:
        error = exc
    finally:
        monitor_stop.set()
        if monitor is not None:
            monitor.join(timeout=1)
            if monitor.is_alive() or monitor_state["violation"]:
                error = error or ValueError(
                    "Embedding resource monitor unsettled or violated"
                )
        if process is not None:
            try:
                worker_settled = _stop_owned(process, psutil, known_children)
            except BaseException:
                worker_settled = False
        safe_to_clear = (
            error is None
            and data_started
            and data_ack
            and cleanup_started
            and cleanup_ack
            and unload_verified
            and worker_settled
            and (monitor is None or not monitor.is_alive())
            and not monitor_state["violation"]
        )
        if safe_to_clear:
            try:
                if any(load(marker) != marker_content for marker in attempt_markers):
                    raise ValueError("Attempt marker changed during execution")
                for marker in attempt_markers:
                    marker.unlink()
            except BaseException as exc:
                error = error or exc
                safe_to_clear = False
                # Restore any marker already removed; never overwrite another owner.
                for marker in attempt_markers:
                    if not marker.exists():
                        try:
                            write_new(marker, marker_content)
                        except FileExistsError:
                            pass
        uncertain = bool(attempt_markers) and not safe_to_clear
        for handle in reversed(leases):
            handle.close()
        settlement = {
            "schema_version": "askmill.embedding-settlement.v1",
            "request_sha256": request_sha256,
            "profile_sha256": profile_sha256,
            "data_requests_started": 1 if data_started else 0,
            "provider_data_requests_confirmed": 1
            if data_ack
            else (None if data_started else 0),
            "data_acknowledged": data_ack,
            "cleanup_requests": 1 if cleanup_started else 0,
            "total_embed_endpoint_requests": int(data_started) + int(cleanup_started),
            "cleanup_acknowledged": cleanup_ack,
            "unload_verified": unload_verified,
            "owned_process_stopped": worker_settled,
            "lease_handles_closed": len(leases),
            "lease_identities": lease_identities,
            "owned_descendants_observed": known_children,
            "elapsed_seconds": time.monotonic() - started,
            "quarantined": uncertain,
            "resource_monitor": monitor_state,
            "monitor_settled": monitor is None or not monitor.is_alive(),
            "error": None if error is None else type(error).__name__,
        }
        write_new(output / "settlement.json", settlement)
    if reservation is not None:
        try:
            confirmed = gate.finalize(reservation, settlement) is True
            write_new(
                output / "ledger-confirmation.json",
                {"request_sha256": request_sha256, "confirmed": confirmed},
            )
            if not confirmed:
                raise ValueError("Host budget ledger did not confirm settlement")
        except BaseException as exc:
            error = error or exc
    if error is not None:
        raise error
    if (
        len(leases) != len(profile.lease_paths)
        or not worker_settled
        or not cleanup_ack
        or not unload_verified
    ):
        raise ValueError("Embedding settlement incomplete")
    try:
        verify_file(profile.context_gate)
        permitted = (
            gate.authorize(profile.model_dump(), request.model_dump(), "after") is True
        )
    except BaseException:
        write_new(
            output / "context-recheck.json",
            {
                "request_sha256": request_sha256,
                "scope_sha256": request.scope_sha256,
                "authorized": False,
            },
        )
        raise
    write_new(
        output / "context-recheck.json",
        {
            "request_sha256": request_sha256,
            "scope_sha256": request.scope_sha256,
            "authorized": permitted,
        },
    )
    if not permitted:
        raise ValueError(
            "Context revoked after embedding; retain artifacts without delivery"
        )
    for label, filename in (
        ("request_ref", "request.json"),
        ("profile_ref", "profile.json"),
        ("runtime_receipt", "runtime.json"),
        ("settlement_receipt", "settlement.json"),
        ("provider_response", "provider-response.json"),
        ("context_recheck", "context-recheck.json"),
        ("ledger_confirmation", "ledger-confirmation.json"),
    ):
        path = output / filename
        result[label] = {"path": str(path), "sha256": sha(path.read_bytes())}
    write_new(output / "result.json", result)
    return result
