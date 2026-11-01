"""Strict, bounded JSON at runner-owned byte boundaries; no domain parsing."""

import json
from pathlib import Path

MAX_REQUEST_BYTES = 4 * 1024 * 1024
MAX_BATCH_BYTES = 8 * 1024 * 1024
MAX_SOURCE_METADATA_BYTES = 512 * 1024
MAX_FROZEN_INPUT_BYTES = 32 * 1024 * 1024
MAX_RECEIPT_BYTES = 96 * 1024 * 1024


def json_size(value, limit):
    size = 0
    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False)
    for chunk in encoder.iterencode(value):
        size += len(chunk.encode("utf-8"))
        if size > limit:
            raise ValueError("JSON exceeds byte budget: " + str(limit))
    return size


def loads(raw, limit=MAX_REQUEST_BYTES):
    if not isinstance(raw, (str, bytes, bytearray)):
        raise ValueError("Provide JSON text or bytes")
    if len(raw.encode("utf-8") if isinstance(raw, str) else raw) > limit:
        raise ValueError("JSON exceeds byte budget: " + str(limit))

    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("Duplicate JSON object key: " + key)
            value[key] = item
        return value

    def constant(value):
        raise ValueError("Non-finite JSON constant: " + value)

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (RecursionError, OverflowError) as error:
        raise ValueError("JSON exceeds parser depth or number budget") from error


def read_bytes(path, limit=MAX_REQUEST_BYTES):
    with Path(path).open("rb") as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Input file exceeds byte budget: " + str(limit))
    return raw


def load(path, limit=MAX_REQUEST_BYTES):
    return loads(read_bytes(path, limit), limit)
