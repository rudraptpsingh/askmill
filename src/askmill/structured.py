"""Bounded, offline JSON Schema subset for candidate responses, never acceptance."""

import hashlib
import json
import math

from jsonschema import Draft202012Validator

DIALECT = "https://json-schema.org/draft/2020-12/schema"
MAX_SCHEMA_BYTES = 128 * 1024
MAX_OUTPUT_BYTES = 1024 * 1024
# No references, regexes, custom formats or vocabularies. Nothing can resolve URLs.
KEYWORDS = {
    "$schema",
    "title",
    "description",
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minProperties",
    "maxProperties",
    "enum",
    "const",
    "anyOf",
    "oneOf",
    "allOf",
    "not",
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def schema_digest(document):
    return hashlib.sha256(canonical(document).encode()).hexdigest()


def bounded_tree(value, *, max_nodes, max_depth):
    stack = [(value, 0)]
    count = 0
    while stack:
        node, depth = stack.pop()
        count += 1
        if count > max_nodes or depth > max_depth:
            raise ValueError("JSON tree exceeds node/depth budget")
        if isinstance(node, dict):
            if any(not isinstance(key, str) for key in node):
                raise ValueError("JSON object keys must be strings")
            stack.extend((item, depth + 1) for item in node.values())
        elif isinstance(node, list):
            stack.extend((item, depth + 1) for item in node)
        elif type(node) not in (str, int, float, bool, type(None)):
            raise ValueError("Use JSON values only")
        elif isinstance(node, float) and not math.isfinite(node):
            raise ValueError("JSON numbers must be finite")


def check_schema(document):
    bounded_tree(document, max_nodes=8192, max_depth=32)
    if len(canonical(document).encode()) > MAX_SCHEMA_BYTES:
        raise ValueError("Response schema exceeds 128 KiB")
    if not isinstance(document, dict) or not document:
        raise ValueError("A nonempty response schema object is required")
    stack = [document]
    while stack:
        node = stack.pop()
        if type(node) is bool:
            continue
        if not isinstance(node, dict):
            raise ValueError("Invalid response subschema")
        unknown = set(node) - KEYWORDS
        if unknown:
            raise ValueError(
                "Unsupported response schema keywords: " + ", ".join(sorted(unknown))
            )
        if "$schema" in node and node["$schema"] != DIALECT:
            raise ValueError("Response schema must use Draft 2020-12")
        properties = node.get("properties", {})
        if not isinstance(properties, dict):
            raise ValueError("Schema properties must be an object")
        stack.extend(properties.values())
        for key in ("items", "additionalProperties", "not"):
            if key in node:
                stack.append(node[key])
        for key in ("anyOf", "oneOf", "allOf"):
            if key in node:
                if not isinstance(node[key], list):
                    raise ValueError("Schema alternatives must be an array")
                stack.extend(node[key])
    try:
        Draft202012Validator.check_schema(document)
    except Exception as error:
        raise ValueError("Invalid Draft 2020-12 response schema") from error


def validate_output(text, document):
    """Keep literal text elsewhere. Never repair, strip fences or coerce values."""

    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("Duplicate JSON object key")
            value[key] = item
        return value

    def constant(value):
        raise ValueError("Non-finite JSON constant")

    try:
        if len(text.encode()) > MAX_OUTPUT_BYTES:
            raise ValueError("Response exceeds 1 MiB validation budget")
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
        bounded_tree(value, max_nodes=20000, max_depth=64)
    except (ValueError, RecursionError, OverflowError):
        return {"valid": False, "errors": ["invalid_json_or_budget"]}
    errors = []
    for error in Draft202012Validator(document).iter_errors(value):
        errors.append(
            "/"
            + "/".join(
                str(p).replace("~", "~0").replace("/", "~1")
                for p in error.absolute_path
            )
            + ":"
            + str(error.validator)
        )
        if len(errors) >= 16:
            break
    return {"valid": not errors, "errors": errors}
