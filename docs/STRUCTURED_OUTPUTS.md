# Structured candidate responses (a4)

Local Ollama can constrain output using the native `api/chat` `format` schema
parameter. AskMill a4 exposes this through the existing leased SDK, JSON CLI
and MCP runner. No direct API bypass or profile migration is required.

The upstream interface is documented in [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs)
and was introduced in [Ollama 0.5.0](https://github.com/ollama/ollama/releases/tag/v0.5.0).
AskMill requires a recognized stable `major.minor.patch` version >=0.5.0,
local model identity and the profile's completion/vision capabilities. MLX,
OpenAI-compatible, cloud-backed and unrecognized/prerelease runtimes are
rejected for this feature. There is no model or provider fallback.

## Versioned SDK contract

```python
from askmill import Request, ResponseSchema
from askmill.runner import Session

schema = ResponseSchema.from_schema({
    "type": "object",
    "properties": {"source_id": {"type": "string", "enum": ["a", "b"]}},
    "required": ["source_id"],
    "additionalProperties": False,
})
task = Request(
    schema_version="askmill.request.v2",
    prompt='Source a: a condition. Source b: an exception. Return the condition source ID as JSON.',
    response_schema=schema,
    max_tokens=256,
)
# Use your existing pinned profile and ALL shared host lease paths.
with Session(profile, store=".local/receipts", lease=shared_lease_paths) as session:
    candidate = session.run(task)
if candidate.complete and candidate.response_validation.valid:
    # Run consumer source-membership, coverage, role and semantic checks here.
    pass
```

`ResponseSchema` contains `schema_version: askmill.response-schema.v1`, the
`document` object and its required `sha256`. The pin is SHA256 of UTF-8
`json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)`
(Python's default `ensure_ascii=True`). `from_schema` computes it; JSON clients
must supply it. A changed schema with an old pin is rejected before inference.
The parent revalidates a snapshot, including caller mutations after construction.
The exact document goes to `format`; AskMill adds no hidden prompt or settings.
Include schema instructions in the prompt when your task requires them.

CLI: serialize the task to a private JSON file and use
`askmill --store /workspace/receipts run --profile NAME --request request.json`.
Exit codes: **0 completed and schema-valid; 3 incomplete; 4 completed but
schema-invalid; 2 runner/configuration failure; 130 cancelled**.

MCP `run` takes the same versioned `response_schema` envelope as an optional
argument and creates request v2. MCP/CLI batches require explicit
`schema_version: askmill.batch.v2` when containing request v2; they can mix v1
and v2 items. A batch containing invalid output is `schema_invalid` unless it
also contains incomplete work, when its status is `incomplete`. Every item's
own result remains available. `run_batch` uses the same warm worker.

The existing v1 request/result/profile wire fields and unstructured provider
payloads are preserved. v1 requests cannot opt into schema enforcement. Use
the new [request](../schemas/request-v2.json), [result](../schemas/result-v2.json),
[batch](../schemas/batch-v2.json) and [response schema](../schemas/response-schema-v1.json)
contracts. Their older files remain unchanged.

## Supported schema subset and validation budgets

The dialect is Draft 2020-12 (the `$schema` declaration is optional). Allowed
keywords are `$schema`, `title`, `description`, `type`, `properties`, `required`,
`additionalProperties`, `items`, `minItems`, `maxItems`, `uniqueItems`,
`minLength`, `maxLength`, `minimum`, `maximum`, `exclusiveMinimum`,
`exclusiveMaximum`, `multipleOf`, `minProperties`, `maxProperties`, `enum`,
`const`, `anyOf`, `oneOf`, `allOf` and `not`. Boolean nested schemas are allowed,
including `items: false` for empty arrays. The root must be a nonempty object.
Property names and enum/const values are data, not schema keywords.

References (including local `$ref`/`$defs`), regex `pattern`, `format`, other
dialects and unknown keywords are explicitly rejected. Schemas are checked
offline; there is no network schema resolution. Dereference a schema outside
AskMill if needed, then explicitly pin the resulting supported document.

Schema limits: 128 KiB canonical bytes, 8,192 JSON tree nodes, depth 32. Output
validation limits: 1 MiB UTF-8, 20,000 JSON nodes, depth 64, at most 16 errors.
The existing token/image/deadline/batch/transport budgets still apply. The local
validator is `jsonschema` 4.x. The provider may reject a schema it cannot compile;
AskMill never drops constraints or retries without `format`.

## Results, receipts and acceptance

Result v2 keeps `complete` as model completion and adds `response_validation`
(`askmill.response-validation.v1`) with `schema_sha256`, `valid` and bounded
error locations/keywords. A response can be incomplete yet syntactically
schema-valid; it still has status `incomplete`. A completed invalid response
has `complete: true` and status `schema_invalid`. Valid completed output still
has `domain_acceptance: unverified`.

Validation parses literal JSON without repairs, coercion, fence stripping or
retries. Duplicate keys, non-finite numbers, malformed JSON and over-budget
output are invalid. Empty/nontext final content is invalid; the original
provider content remains in the raw receipt. Truncated text remains unchanged.

Receipt v2 freezes the complete versioned request/schema/pin, profile/model
digest, raw provider response and result. Cache identity includes these inputs,
runtime versions, transport SHA, local validator version and structured
validation implementation SHA. A change in schema, prompt, sources or budget
creates a new identity. Replays recheck the stored validation as well as receipt
integrity. Invalid and incomplete results replay unchanged; callers request a
fresh attempt by explicitly changing their task/budget. Old receipts are never
rewritten. Checksums do not authenticate a store against an authorized writer.

An acknowledged invalid response does not quarantine the GPU: it is a completed
transport attempt. Timeouts, unknown external settlement and owned-worker
cleanup retain their existing lease/quarantine rules.

PDF2Data owns original reopening, source-scope/rules/prompt pins, ID membership,
coverage, cross-field roles, literal projection and semantic acceptance. Model
completion and schema validity cannot grant source, legal, client or production
approval. Its semantic extractor adoption is pending explicit owner validation
from the released wheel. Existing Regulatory delivery and consumer pins remain
independent of this opt-in feature.
