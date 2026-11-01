# MCP request parity and producer identity (a6)

Use `run_request_v1` for a complete `askmill.request.v1` or
`askmill.request.v2`, including source IDs/references/hashes and the response
schema. The wrapper contract is `askmill.mcp-run-request.v1` and its input
schema has ID `urn:askmill:mcp-run-request:v1`.

```python
# actual_request is the independently verified real CLI --request JSON object.
result = await client.call_tool(
    "run_request_v1", {"profile": pinned_profile_name, "request": actual_request}
)
```

The tool validates the same `Request` type and calls the same
`Session(profile, store, lease).run(request)` path as the SDK and CLI. Its
typed input schema advertises source/count/field limits. Runtime validation
also enforces byte budgets, unique source IDs and version/schema coherence.
All provided source metadata is frozen into the normal request/receipt/cache
identity; there is no MCP-specific runner, model fallback or rewritten prompt.

Existing `run` and `run_batch` names remain. `run` is the original flat prompt,
images and generation-budget convenience tool, with optional response schema;
it does not accept sources or a complete request. `run_batch` already accepts
complete request dictionaries, including sources, and requires explicit
`askmill.batch.v2` when containing request v2. Its source metadata was not lost
by the old single-call limitation.

All three tools now reject unknown top-level arguments instead of letting the
SDK discard them. Argument objects are bounded to 8 MiB before tool execution;
single requests additionally retain the 4 MiB request, 128-source and 512 KiB
source-metadata admission gates. Argument-shape, duplicate-source-ID,
unknown-field, source-count and JSON-byte faults are refused before `Session`
construction. Actual image bytes and provider/device identity are checked in
the shared Session path; caller source/context preflight remains required.
Error summaries name the failed gate without echoing an entire source-bound
argument object.
MCP SDK framing owns its raw JSON-RPC byte parser; this does not claim new
duplicate-key detection for bytes the SDK has already parsed.

## Identity and exact pins

Initialize `serverInfo.name` is `AskMill`; `serverInfo.version` is the installed
AskMill application version. It no longer falls back to the SDK's own version.
Read the JSON resource `askmill://producer` for `askmill.mcp-producer.v1`:

- `application` / `application_version` identify AskMill;
- `mcp_sdk_version` separately identifies the installed protocol SDK;
- `full_request_tool` / `full_request_tool_contract` identify the wrapper;
- `request_contracts` lists v1/v2; `domain_acceptance` remains `unverified`.

Consumers pin the wheel/application version, SDK version and actual
`tools/list` schemas before use. Reference schemas ship as
[mcp-run-request-v1.json](../schemas/mcp-run-request-v1.json) and
[mcp-producer-v1.json](../schemas/mcp-producer-v1.json). Runtime-generated tool
schema details may also depend on the pinned SDK/Pydantic versions. The metadata
resource is not authentication, source approval or a substitute for receipts.

a6's optional MCP extra requires `mcp>=1.30,<2`. A lower-bound probe found
SDK 1.12 fails import with current Pydantic 2.14; it is not advertised as an a6
qualified combination. This optional dependency change does not upgrade an
existing pinned environment or consumer job automatically.

## Qualified scope

Actual stdio tests use the unchanged real CERC request and a `Session` guard
that stops before inference. They verify full-request and existing batch
metadata reach the shared boundary unchanged, eight malformed-envelope refusal
controls run before a session, and initialize/resource application and SDK
versions are distinct. No model response is mocked or generated. The guard
returns an intentional error, not a fabricated successful result.

This qualifies discovery, identity and admission/refusal parity. Live
source-bound generation, new model receipts, cache adoption, host authorization,
source quality, semantic/numeric/legal approval and the customer's review
state require their separate consumer gates. The previous CLI/SDK/lease/cache
and output contracts remain unchanged; `complete` and response-schema validity
never grant domain acceptance.

Discovery/admission guards and source-only execution have separate scopes.
Use [the execution-mode guidance](EXECUTION_MODES.md) to distinguish zero model
dispatch from runner initialization, receipt replay and source/domain approval.
