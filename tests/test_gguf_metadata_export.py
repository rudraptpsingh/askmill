"""Metadata/container boundary controls; no model or source accuracy claims."""

import hashlib
import importlib.util
import io
from pathlib import Path
import struct

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "gguf_export", ROOT / "tools/gguf_metadata_export.py"
)
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


def string(value):
    return struct.pack("<Q", len(value)) + value


def fixture_bytes():
    # Minimal software envelope, not a fabricated document or usable model.
    fields = string(b"tokenizer.ggml.model") + struct.pack("<I", 8) + string(b"gpt2")
    fields += (
        string(b"tokenizer.ggml.tokens")
        + struct.pack("<IIQ", 9, 8, 1)
        + string(b"control")
    )
    return b"GGUF" + struct.pack(
        "<IQQ", 3, 1, 2
    ) + fields, b"CONTROL_NOT_MODEL_TENSOR_PAYLOAD"


def test_export_preserves_metadata_but_never_copies_payload(tmp_path):
    prefix, payload = fixture_bytes()
    container = tmp_path / "container.gguf"
    raw = prefix + payload
    container.write_bytes(raw)
    report = exporter.export(
        container, hashlib.sha256(raw).hexdigest(), tmp_path / "export"
    )
    sidecar = Path(report["sidecar"]["path"]).read_bytes()
    assert sidecar[:8] == prefix[:8]
    assert sidecar[8:16] == b"\0" * 8
    assert sidecar[16 : len(prefix)] == prefix[16:]
    assert payload not in sidecar
    assert report["metadata_bytes_read"] == len(prefix)
    assert report["file_io"]["container_bytes_read_for_identity_hash"] == len(raw)
    assert container.read_bytes() == raw
    assert report["boundaries"]["tensor_model_loaded"] is False


def test_wrong_identity_creates_no_export(tmp_path):
    prefix, payload = fixture_bytes()
    container = tmp_path / "container.gguf"
    container.write_bytes(prefix + payload)
    with pytest.raises(ValueError, match="hash differs"):
        exporter.export(container, "0" * 64, tmp_path / "export")
    assert not (tmp_path / "export").exists()


def test_declared_string_size_refused_before_body_read():
    data = io.BytesIO(struct.pack("<Q", exporter.MAX_METADATA_BYTES + 1))
    reader = exporter.MetadataReader(data)
    with pytest.raises(ValueError, match="byte bound"):
        reader.string()
    assert data.tell() == 8


def test_declared_array_count_refused_before_elements_read():
    data = io.BytesIO(struct.pack("<IQ", 8, exporter.MAX_ELEMENTS + 1))
    with pytest.raises(ValueError, match="element bound"):
        exporter.MetadataReader(data).value(9)
    assert data.tell() == 12


def test_truncation_refuses_before_output(tmp_path):
    container = tmp_path / "bad.gguf"
    container.write_bytes(b"GGUF")
    with pytest.raises(ValueError, match="Truncated"):
        exporter.export(container, "0" * 64, tmp_path / "export")
    assert not (tmp_path / "export").exists()


def test_cpu_helper_refuses_tensor_container_before_vocabulary_load(tmp_path):
    import os
    import subprocess

    executable = os.environ.get("ASKMILL_CPU_TOKENIZER")
    if not executable:
        pytest.skip("Supply the separately built CPU-only helper")
    prefix, payload = fixture_bytes()
    container = tmp_path / "tensor-bearing.gguf"
    container.write_bytes(prefix + payload)
    prompt = tmp_path / "input.txt"
    prompt.write_text("existing software control")
    result = subprocess.run(
        [executable, str(container), str(prompt), "0"], capture_output=True, timeout=10
    )
    assert result.returncode == 2
    assert b"Refuse tensor-bearing container" in result.stderr
    assert result.stdout == b""
    assert container.read_bytes() == prefix + payload
