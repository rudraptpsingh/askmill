# Bounded-model tracker alignment (P0)

Status: producer-side P0 contract proposal. This document changes no runtime,
released schema, profile, default model, lease, receipt or historical result.
Map owns the document ledger and coverage/accuracy reporting; the consuming
task owner owns source acceptance and review. No model execution, historical
backfill or new ledger document is authorized by this alignment.

## Invocation boundary

Future bounded tasks use the existing `run_request_v1` MCP tool with exactly
`{profile, request}`. Preserve the closed wrapper/Request/Source schemas and
pinned `askmill.mcp-run-request.v1` identity. Do not insert authority, capacity,
tracker, review or atom-selection controls into that argument object.
The consumer's separate, pinned execution descriptor binds those controls to
the exact request/profile/model/runtime and Map requirements version.

Use Request v2 with a pinned supported response-schema document for structured
candidates. Close output objects and enumerate only the allowed source atom
IDs/relations. The source owner supplies the frozen atom set and required
prerequisite/exception/alternative anchors. Sources metadata is provenance;
AskMill does not turn it into prompt context. Full caller canonical checks stay
separate from the provider grammar's supported subset. Do not strip constraints
from a frozen request or infer a schema pass from completed JSON alone.

P3 proviso ownership and old/new atom selection remain gated. P4 disposition
selection remains gated separately. A future disposition value such as
`accepted` describes the source decision; it is not the review outcome of the
model candidate. Whole-section role runs, invented legal text, new models and
default migrations are outside this P0 alignment.

## Capacity and authority boundary

Keep schema admission, tokenizer/rendering qualification, static fit, execution
authority, live context/output evidence and caller review distinct.
The no-container-read helper may report unknown; bytes/codepoints are not token
counts. A separately qualified upstream renderer's count is static evidence,
not running-provider allocation or source-to-binary equivalence.
A later authorized run retains actual input count, allocated context, output
count/finish and both AskMill/owned-service cleanup receipts. Missing evidence,
clipping, unexplained count mismatch and incomplete output cannot be promoted.
Neither static fit nor a call cap grants permission to dispatch.

## Document and invocation identity

Map's unit is one `powerlex.tracker.document-run.v1` record per actual original
PDF SHA-256. The caller supplies that original hash, body and workbook profile.
Do not substitute an arbitrary Request.sources content hash: it may identify a
processed reading or atom bundle rather than the original PDF.

One original can have multiple immutable invocations. Deduplicate by invocation
ID and receipt/attempt identity; preserve failed, refused and incomplete
attempts. Replay is a new invocation referencing the original model receipt,
not a fresh model call. For old/new comparison over multiple originals, attach
references to every source, but attribute time/tokens/calls once to a named
primary document and deduplicate globally by invocation ID. Never multiply one
call across document rows or count it as a new original/accuracy case.

Map/Central's accepted writer merges run references into the existing document
record without overwriting other tools' stages or prior runs. AskMill does not
write another owner's worktree or create a parallel coverage dashboard.

## Proposed Map extension — acceptance required

The inspected document-run v1 README has no model-stage/token/review contract;
the generator uses a fixed pipeline that omits an `askmill` stage. Adding
unagreed fields would not make them appear in tracker output. Map must accept
an additive model-stage/history projection (or provide an equivalent explicit
schema) before any adapter writes it. The proposed location is
`stages.askmill`, with immutable `runs[]` references and a summary. These are
proposed fields, not additions to AskMill's released Request/Result schemas:

| Field group | Meaning/source |
|---|---|
| `status`, `receipt`, `version` | Pending/done/held/failed stage and a real pinned run/failure artifact; no receipt means pending |
| `runs[].invocation_id`, `attempt_id`, `receipt_id`, `replayed` | Invocation versus actual model-attempt/cache identity; unknown attempt IDs stay null |
| `runs[].task`, `phase`, `primary_document_sha256`, `source_document_sha256s` | Explicit bounded task/phase and original-document attribution, supplied by the caller |
| `runs[].pins` | Original/reading/atom-set, requirements, request, profile/model/runtime, provider/canonical schemas, authority, capacity and review receipt hashes |
| `runs[].transport_status`, `complete`, `schema_valid` | Actual transport/completion/provider-schema outcome, not source or legal acceptance |
| `runs[].model_calls` | Observed fresh dispatch count; zero for proved pre-dispatch refusal/cache replay, null when unproved; never infer from generic port-call count |
| `runs[].tokens.input`, `output`, `reserved_output`, `declared_context`, `allocated_context` | Actual provider counts separately from requested budgets; unavailable measurements stay null |
| `runs[].timings` | Current invocation wall time, Session.run time, fresh model/provider time, load/prefill/generation and preflight time with explicit units/basis |
| `runs[].review.status`, `scope`, `receipt`, `reviewer` | Caller-owned pending/accepted/rejected/partial/not-run decision bound to the exact candidate and source scope |
| `runs[].review.accepted_candidates`, `rejected_candidates`, `unreviewed_candidates` | Counts only when established by a bound review; no inference from model agreement, completion or schema validity |
| `runs[].holds`, `settlement` | Existing source/client/current-law holds and attempt/owned-service cleanup; no implied clearance |

Required Map decision: accept the stage/history fields and renderer projection,
including null/unknowns and multi-document deduplication, or return its exact
alternative. The ledger currently documents stage receipts as paths; retaining
SHA-256 pins alongside them needs agreement too. No adapter or stage rendering
is claimed implemented by this document.

## Measurement mapping

| Available AskMill evidence | Proposed ledger meaning |
|---|---|
| Caller dispatch/finish monotonic measurement | `invocation_wall_seconds`; use as stage wall time only with an explicit attribution rule |
| `Result.seconds` | `session_run_seconds`; excludes Session startup and receipt finalization, and is not extraction time |
| Fresh Ollama raw `total_duration / 1e9` | `model_seconds`, including provider load; null when provider measurement is absent |
| Fresh raw `load_duration`, `prompt_eval_duration`, `eval_duration` | Separate `load_seconds`, `prefill_seconds`, `generation_seconds`; do not add them again to total |
| Raw `prompt_eval_count`, `eval_count` | Actual input/output tokens; keep distinct from `request.max_tokens` and profile context |
| Current preflight receipt measurement | `preflight_seconds` with its declared scope; metadata-export/setup I/O and time stay separate |
| Replayed model receipt | Current fresh model calls/time/tokens are zero; retain prior observed counters/timing as referenced historical evidence, not a new measurement |
| No dispatch / failed CLI before Session | Model calls zero only with proof; retain caller failure wall time and artifact, not an invented model Result/settlement |
| Timeout or lost provider acknowledgement | Preserve incomplete/error and cleanup uncertainty; unobserved counts/durations remain null, not zero |

Keep PDF2Data extraction time in `stages.pdf2data.seconds`; model time must not
inflate extraction throughput or disappear into it. Warm/cold classification
requires evidence; absence of `warm: true` does not establish a measured cold
run. Map must support unknown temperature/cache state explicitly.

## Outcome and progress rules

A transport-completed/schema-valid run starts caller review as pending. Accepted
candidate associations require the consumer's canonical and required-anchor
checks plus its bound independent source review. Rejection needs a stage/reason
and target receipt; acceptance never implies approved legal applicability,
client identity/facts, money or publication. Preserve current holds.

Do not set `stages.query.outcome = accepted` to record an accepted model request
or association. Query alone reports an accepted semantic answer. Field acceptance
and gold checks remain Map/reviewer-owned; model calls, software tests, contract
alignment and releases do not increase document coverage or accuracy.
Software controls and historical development cases remain excluded from real
independent accuracy. P0 emits no document-run row and changes no tracker total.

The current released interfaces remain described in [MCP.md](MCP.md),
[EXECUTION_MODES.md](EXECUTION_MODES.md), [CAPACITY_PREFLIGHT.md](CAPACITY_PREFLIGHT.md)
and [OFFLINE_QWEN_QUALIFICATION.md](OFFLINE_QWEN_QUALIFICATION.md).
