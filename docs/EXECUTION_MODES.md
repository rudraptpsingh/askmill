# Execution modes, authorization and retained evidence

AskMill a6 remains the qualified release. Consumers choose the authorized route
before constructing a runner. A maximum call/token cap bounds an already
authorized dispatch; it does not authorize initialization, inference, a retry,
fallback, source access or publication. Honor existing user and host decisions
without adding a new permission prompt for work already authorized.

## Choose the route before a Session

| Route | Runner/device activity | Evidence and limits |
|---|---|---|
| Host `source_rules_only` | No AskMill runtime, Session, GPU lease, warmup, embedding or model dispatch | Use the host's admitted native/source rules; unmatched or insufficient context stays unknown/refused |
| Separately authorized configuration inspection | `--version`, `list` and `doctor` do not open a Session | Doctor reports `configuration_valid` and `inference_tested:false`; it does not attest model execution or source acceptance |
| MCP discovery/identity inspection | Initialize, tools/list and `askmill://producer` open no Session | This is protocol identity/admission evidence, not a model result; do not start it as an implicit fallback inside a source-only request |
| Offline frozen-artifact qualification | Pure request/receipt validation needs no Session or provider call | Caller supplies exact expected request/profile/runtime/settlement pins and authorized private evidence; this does not qualify live generation/cache adoption |
| Session receipt replay | Session acquires the configured leases, verifies runtime/model identity and starts its worker | A matching receipt reuses a prior result; a cache miss can generate. This route is not a zero-runner-initialization mode |
| Authorized fresh inference | `run`, `batch`, `read-fields` and MCP model tools use their configured shared Session | Preserve actual mode, scope, budgets, model/runtime identity, dispatch and settlement; completion/schema validity remain domain-unverified |

The current Query `source_rules_only` integration intentionally omits AskMill
runtime/qualification inputs and initializes no AI runner. Leave that policy
in Query; do not duplicate it in AskMill or create a runner to check a cache,
warm a model, or turn an unmatched source question into inference. A generic
SDK structured-output port call can perform deterministic source projection
while actual model calls remain zero. Record those counters separately.

AskMill's model commands have no `replay_only`, `no_inference` or `dry_run`
switch. `max_tokens=0` is invalid input, not an execution policy. Source-only
hosts should not call a model command in the hope that it will hit a cache.
Host `selection_mode` and call-cap fields are host policy, not extra Request or
MCP arguments; unknown fields are rejected. Request preparation, a valid schema,
tool availability and spare call budget do not change the chosen host mode.

## Authorized model work

Perform cheap input/source/context/permission checks before the Session. Use
the already authorized scope and actual source/profile/rule/schema/model pins.
Missing required tables, EM inputs, governing versions or reviewed client
inputs remain explicit blockers for dependent interpretation. Revalidate scope
and cancellation/revocation state after asynchronous work and before releasing
output. These decisions remain with the consumer, not a new authorization hook
inside the runner.

Pass **all** existing host device lease paths. Nonblocking `busy` or
`cleanup_uncertain` is a retained outcome, not permission to use a different
lock, clear a quarantine or switch provider. Source-only work needs no GPU
lease. A client timeout/disconnect does not prove an external generation has
stopped; retain its unsettled state until the owning operator independently
establishes settlement. AskMill stops its own worker, not the external service.

## Retain the correct evidence

| Outcome | Native AskMill evidence | Additional caller evidence |
|---|---|---|
| Completed, schema-invalid or incomplete generation | Immutable request/profile/runtime/result receipt; v2 retains raw Ollama output | Scope/mode authorization, original/source reading, rule/schema pins and independent domain checks |
| Settled Session | Separate integrity-checked settlement with worker/ownership/session and profile/lease/runtime bindings | Bind the invocation to the relevant settlement; do not infer cleanup from result existence |
| Input refusal before Session | CLI error JSON/exit or MCP `isError`; a model-result receipt need not exist | Preserve the exact failed request pin, invocation, stdout/stderr or protocol error, return/cancel state and monotonic interval |
| Timeout, cancellation, provider error or unknown cleanup | Existing committed items/settlements/quarantine may exist; not every failure has a model-result receipt | Retain the failed invocation and error artifacts without inventing a receipt/result or declaring cleanup confirmed |

Never repair, overwrite, relabel or delete a failed/truncated record to pass a
gate. Store caller failure envelopes alongside frozen receipts, with their own
hashes; they are caller records, not fabricated `askmill.result` objects.
Receipt checksums are integrity checks, not authentication or domain approval.

SDK `Session.run` returns before the surrounding Session has closed. Wait for
the relevant settlement before asserting cleanup. Replay keeps the original
attempt/session identifiers: its original settlement proves the original
worker's cleanup, not the current replay invocation's lifecycle. SDK callers
can retain the current Session ID and its settlement separately. CLI/MCP replay
results do not add a current-session ID; keep the consumer invocation envelope
and any independently bound current settlement rather than guessing ownership
from the cached result's original ID. If that binding is unavailable, leave the
corresponding live-execution acceptance unknown.

## Keep counters and acceptance separate

Record source-rule/structured-port operations, runner initializations, actual
model/embedding dispatches, cache replays and settlement state independently.
`not_started` is appropriate when a source-only route never created model
resources; it is not a fabricated acknowledged model settlement.

Retained `Result.seconds`, provider tokens and load/cache counters describe the
original generation. Measure the current invocation's monotonic interval and
actual request/response artifact bytes separately. Declare the exact boundary
when raw wire-byte counters are unavailable. Repeated inputs, admission guards,
refusal controls and replay add no independent document/answer accuracy cases.
With insufficient matched real samples, latency thresholds and p95 remain
`not_established`.

Input schema, completion, output schema, scope authorization, resource cleanup,
source/semantic/numeric/legal correctness and client review are separate gates.
No successful local model result approves eligibility, money or duties. Keep
the current client and report/docket publication holds until their owners
validate the actual source evidence and explicitly approve the relevant scope.
