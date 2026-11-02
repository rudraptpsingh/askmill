"""Explicit GGUF metadata-only export plus full-container streaming identity.

This separate stage reads container bytes for hashing. It never loads tensors
into a model, starts a provider or acquires GPU leases. Output stays private.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct

MAX_METADATA_BYTES = 64 * 1024 * 1024
MAX_FIELDS = 4096
MAX_ELEMENTS = 1024 * 1024
SCALARS = {
    0: "B",
    1: "b",
    2: "H",
    3: "h",
    4: "I",
    5: "i",
    6: "f",
    7: "?",
    10: "Q",
    11: "q",
    12: "d",
}


class MetadataReader:
    def __init__(self, handle, limit=MAX_METADATA_BYTES):
        self.handle = handle
        self.limit = limit
        self.raw = bytearray()

    def read(self, count):
        if count < 0 or len(self.raw) + count > self.limit:
            raise ValueError("GGUF metadata exceeds explicit byte bound")
        raw = self.handle.read(count)
        if len(raw) != count:
            raise ValueError("Truncated GGUF metadata")
        self.raw.extend(raw)
        return raw

    def number(self, fmt):
        return struct.unpack("<" + fmt, self.read(struct.calcsize("<" + fmt)))[0]

    def string(self):
        return self.read(self.number("Q"))

    def value(self, kind, depth=0):
        if kind in SCALARS:
            return self.number(SCALARS[kind])
        if kind == 8:
            data = self.string()
            return {
                "string_sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
            }
        if kind == 9:
            element_type, count = self.number("I"), self.number("Q")
            if depth >= 2 or count > MAX_ELEMENTS:
                raise ValueError("GGUF array exceeds depth/element bound")
            if element_type in SCALARS:
                self.read(count * struct.calcsize("<" + SCALARS[element_type]))
            else:
                for _ in range(count):
                    self.value(element_type, depth + 1)
            return {"element_type": element_type, "elements": count}
        raise ValueError("Unsupported GGUF value type")

    def metadata(self):
        if self.read(4) != b"GGUF":
            raise ValueError("Only little-endian GGUF is supported")
        version = self.number("I")
        if version not in (2, 3):
            raise ValueError("Unsupported GGUF version")
        tensors, count = self.number("Q"), self.number("Q")
        if count > MAX_FIELDS:
            raise ValueError("GGUF field count exceeds bound")
        fields = {}
        for _ in range(count):
            key = self.string().decode("utf-8")
            if len(key) > 4096 or key in fields:
                raise ValueError("Invalid or duplicate GGUF metadata key")
            kind = self.number("I")
            fields[key] = {"type": kind, "summary": self.value(kind)}
        return version, tensors, fields


def export(container, expected_sha256, output):
    if not re.fullmatch("[a-f0-9]{64}", expected_sha256):
        raise ValueError("Supply the exact expected container SHA-256")
    output = Path(output)
    if output.exists():
        raise ValueError("Output directory must be new")
    container = Path(container).resolve()
    with container.open("rb") as handle:
        before = os.fstat(handle.fileno())
        reader = MetadataReader(handle)
        version, tensors, fields = reader.metadata()
        prefix = bytes(reader.raw)
        if not {"tokenizer.ggml.model", "tokenizer.ggml.tokens"} <= fields.keys():
            raise ValueError("Missing GGUF tokenizer metadata")
        handle.seek(0)
        full_hash, prefix_hash = hashlib.sha256(), hashlib.sha256()
        hashed_bytes, prefix_remaining = 0, len(prefix)
        while chunk := handle.read(8 * 1024 * 1024):
            full_hash.update(chunk)
            hashed_bytes += len(chunk)
            if prefix_remaining:
                prefix_hash.update(chunk[:prefix_remaining])
                prefix_remaining = max(0, prefix_remaining - len(chunk))
        after = os.fstat(handle.fileno())

        def stable(stat):
            return (
                stat.st_dev,
                stat.st_ino,
                stat.st_size,
                stat.st_mtime_ns,
                stat.st_ctime_ns,
            )

        if (
            stable(before) != stable(after)
            or prefix_hash.hexdigest() != hashlib.sha256(prefix).hexdigest()
        ):
            raise ValueError("Container changed while exporting/hashing")
        if full_hash.hexdigest() != expected_sha256:
            raise ValueError("Container hash differs from declared identity")
    # Preserve every metadata field byte; declare zero tensors and add alignment.
    metadata_only = prefix[:8] + struct.pack("<Q", 0) + prefix[16:]
    alignment = fields.get("general.alignment", {}).get("summary", 32)
    if type(alignment) is not int or not 1 <= alignment <= 4096:
        raise ValueError("Unqualified GGUF alignment")
    metadata_only += b"\0" * (-len(metadata_only) % alignment)
    output.mkdir(parents=True)
    sidecar = output / "tokenizer-metadata.gguf"
    with sidecar.open("xb") as handle:
        handle.write(metadata_only)
    report = {
        "schema_version": "askmill.gguf-metadata-export.v1",
        "container": {
            "path": str(container),
            "sha256": full_hash.hexdigest(),
            "bytes": hashed_bytes,
        },
        "gguf_version": version,
        "original_tensor_count": tensors,
        "exported_tensor_count": 0,
        "metadata_bytes_read": len(prefix),
        "metadata_byte_limit": MAX_METADATA_BYTES,
        "original_metadata_prefix_sha256": hashlib.sha256(prefix).hexdigest(),
        "all_metadata_field_bytes_preserved": True,
        "metadata_fields": fields,
        "sidecar": {
            "path": str(sidecar.resolve()),
            "sha256": hashlib.sha256(metadata_only).hexdigest(),
            "bytes": len(metadata_only),
        },
        "file_io": {
            "container_bytes_read_for_identity_hash": hashed_bytes,
            "container_metadata_bytes_read_for_export": len(prefix),
            "tensor_payload_bytes_read_only_as_hash_stream": True,
            "tensor_payload_copied_to_sidecar": False,
        },
        "boundaries": {
            "tensor_model_loaded": False,
            "Session_initialized": False,
            "provider_calls": 0,
            "model_inference": 0,
            "gpu_lease_acquired_or_bypassed": False,
            "execution_authorized": False,
            "static_fit_qualified": False,
        },
        "utility_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    with (output / "export.json").open("x") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = export(args.container, args.expected_sha256, args.output)
    print(
        json.dumps(
            {
                k: report[k]
                for k in [
                    "schema_version",
                    "container",
                    "sidecar",
                    "file_io",
                    "boundaries",
                ]
            }
        )
    )


if __name__ == "__main__":
    main()
