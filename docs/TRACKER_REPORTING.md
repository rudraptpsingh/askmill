# Retained-invocation reporting 0.1.0

`tools/tracker_report.py` projects retained AskMill receipts and proved
pre-dispatch failures into Map intake 1.1. It does not create a Session, contact
a provider, acquire a device lease, change defaults or execute a model. It emits
an owner outbox; Map's installed validator/writer owns intake and registration.

This is a separately versioned tool-only adapter. The inference package remains
AskMill v0.1.0a6; existing launchers, jobs, profiles and shared leases stay pinned.
Use a separately qualified a6 interpreter and the adapter from the immutable
`tracker-reporting-v0.1.0` archive, not an unversioned checkout copy. Map intake
qualification uses downloaded Map v0.37.0 and its packaged requirements artifact.

## CLI

```sh
/path/to/pinned-a6/bin/python /path/to/installed/tools/tracker_report.py \
  --descriptor /path/to/private/projection.json \
  --descriptor-sha256 EXACT_DESCRIPTOR_BYTE_SHA256 \
  --evidence-root OWNER=/path/to/authorized/evidence/root \
  --output /path/to/private/new-outbox
```

Repeat `--evidence-root` for each authorized repository. References use exactly
`{repository, path, sha256}`, with an optional `subject_pointer`. Paths are
portable and relative to an explicit root; missing/changed evidence and escapes
are refused. Native envelope hashes and cache-key/input/profile/runtime identity
are rechecked. Output goes to a new directory, never over an old receipt.
A successful projection writes `runs.ndjson` and `projection.json`; exit 0
means projection completed, not domain acceptance. Source/provenance refusal
writes `refusal.json`, emits zero records and exits 2. Setup failures may have
only stderr; keep the descriptor pin and failure evidence.

Then use Map's independently pinned CLI, requirements bytes and the same roots:

```sh
/path/to/installed-map/bin/python -m powerlex_map.tracker_ledger validate \
  --records-jsonl /path/to/private/new-outbox/runs.ndjson \
  --requirements /path/to/installed/requirements.v1.json \
  --expected-requirements-sha256 EXACT_REQUIREMENTS_SHA256 \
  --evidence-root OWNER=/path/to/authorized/evidence/root
```

Only the accepted Map/Central writer registers the owner outbox into the golden
tracker. Local qualification ledgers are controls, not a parallel coverage
report. Registration, identical replay and shared invocation aggregation must
be qualified against the installed Map release.

## Descriptor `askmill.tracker-projection.v1`

The descriptor is closed. Its required root fields are `schema_version`,
`run_id_prefix`, `pipeline_run_id`, `recorded_at`, `requirements_sha256`,
`primary_document_sha256`, `documents` and `invocation`. Optional fields are
`review` and `extra_pins`. Profile/body selection is supplied by the owner and
validated against Map requirements at intake; the adapter does not infer it.

Each document has exactly `sha256`, `title`, `profile_id`, `body`,
`original_receipt` and `holds`. The original receipt's explicit subject pointer
must reopen that full original SHA-256. A processed-reading/source-metadata hash
cannot substitute for the original. Titles and holds are retained caller data.

A model invocation has `kind: model_receipt`, `receipt` and `source_binding`.
Optional `result` references an actual archived CLI/MCP Result for a replay;
optional `settlement` references current invocation cleanup. Optional
`allocated_context` has `receipt`, `pointer` and `revision_pointer`; the model
revision must match before an allocated-context count is projected.

`source_binding` has `prompt_json_byte_start`, `prompt_json_byte_length`,
`json_sha256` and `subject_pointers`. The adapter reopens that exact structured
JSON slice of the frozen prompt and requires its source subjects to equal the
attributed originals. It does not search text or guess a source assignment.
An original appearing elsewhere in reader context but absent from that frozen
source payload is refused. Unstructured historical prompts lacking this
provenance are not eligible for an inferred document association. JSON pointers
are caller-defined source handles; this verifies bytes/identity, not legal truth
or whether a source excerpt is sufficient for a claim.

A pre-dispatch failure has `kind: pre_dispatch_failure`, `receipt`,
`model_calls_pointer`, `request`, `profile_registry`, `profile_name`, `runtime`
and `source_binding`. The failure receipt must explicitly prove integer zero
model calls. No AskMill Result or cleanup receipt is fabricated. Unproved
historical call counts are not zero; unsupported failure shapes are refused.

`extra_pins` maps named hash bindings to structured references. They may retain
external authority, capacity, atom-set or review prerequisites without adding
fields to the closed `run_request_v1` arguments.

Optional `review` has only `receipt`, `pointer` and `target_pointer`. Reopened
review data must contain the exact status (`accepted`, `rejected`, `partial`),
named reviewer and nullable accepted/rejected/unreviewed candidate counts; the
target must match the reported invocation evidence's byte SHA. Descriptor flags
cannot invent a decision. This is integrity checking, not reviewer authentication.
Without a review, a model result stays `pending`; a proved pre-dispatch failure
is `not_run`. No review status implies source, translation, numeric, legal,
client-fact, applicability, money or publication approval.

## Projection and measurement

One source original gets one document-run record per immutable invocation event.
Each has `record_version: 1.1`, `tool: askmill`, only an `askmill` stage and
`gold.kind: none`. Historical wall intervals stay null with `not_recorded`
basis/reason; native measured values stay in separate timing fields. This does
not create or promote PDF2Data/Map/Query/Impact stages or profile processing.

| Evidence | Projected meaning |
|---|---|
| Native `prompt_eval_count`, `eval_count` | Observed input/output tokens; missing stays null |
| Request `max_tokens`, profile context | Reserved output and declared context, not observed work |
| Pinned allocation receipt | Allocated context only after revision binding |
| `Result.seconds` | Session-run time, not extraction time or a complete invocation wall interval |
| Raw provider nanoseconds | Separate model/load/prefill/generation seconds; no fallback from Session time |
| Absent parser/preflight measurements | Not invented or copied from model time |
| Actual replay Result | Zero new model calls/tokens/model time; original receipt retained as replay reference |
| Replay with cached-origin settlement | Refused as proof of current invocation cleanup |
| Proved pre-dispatch failure | Zero model calls/model time; unobserved tokens, Session and allocation stay null |

Invocation ID derives from the original attempt, actual replay-result byte pin
or failure-evidence byte pin. For genuinely linked PDFs, every record carries
the same invocation object and complete source list, with one primary original.
Map deduplicates these metrics globally by invocation ID and rejects conflicting
metrics. Repeated delivery cannot multiply calls, tokens or time. Preserved
source holds and caller review remain separate from transport/schema status.

## Qualified scope and remaining gates

Local source and installed-artifact qualification reopens actual retained
complete-model and pre-dispatch-failure receipts. Map 0.37 validation, append,
zero-insert replay, batch registration and readback preserve one original and
separate model/caller-review counters. An unrelated real companion PDF receives
a source-bound refusal. Multi-PDF aggregation, replay, nullable counters and
review-decision substitutions are software controls using mutations of retained
evidence; they are not new real model invocations, source associations, gold
cases or accuracy observations. No actual historical replay is invented.

The adapter performs no current extraction/inference and grants no global
tracker registration by itself. Final owner registration and consumer acceptance
are separate pinned receipts. P3/P4 atom tasks remain gated; any later model
work still uses [the closed MCP boundary](MCP.md), external capacity/authority,
required-anchor checks and caller-owned review.
