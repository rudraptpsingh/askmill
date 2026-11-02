# AskMill implementation and validation

Goal: create an open-source local text/vision runner with portable profiles,
bounded sessions, immutable receipts, CLI, optional MCP/skill and PDF2Data
compatibility; record validation and remaining hardware/product gates.

| Phase | Goal | Acceptance outcome |
|---|---|---|
| 1 | Independent public repo and portable contracts | MIT repo; clean package build; versioned profile/request/batch/result schemas; no model dependencies required for base install |
| 2 | Bounded warm execution and receipts | One load across a batch; frozen image/prompt/settings; atomic receipts and replay; corrupted receipts rejected; runtime changes invalidate cache |
| 3 | Providers and resource ownership | Real MLX vision and Ollama text runs; shared leases; cloud-backed Ollama rejected; interrupt/timeout/parent-crash checks; separate settlement receipts |
| 4 | Callers and PDF2Data | CLI and MCP batch calls; installed skill; published PDF2Data field-witness API adapter; separate legacy-branch conformance checks |
| 5 | Qualification and handoff | Source and clean-wheel suites; three Python CI versions; published consumer CI; real bounded code finding independently tested; exact release evidence below |

## Current validation, 1 November 2026

- Core suite: **29 passed** without PDF2Data; optional consumer modules skip.
- Published PDF2Data environment: **33 passed**, with the legacy-only module
  skipped. Four integration cases use actual native PDF extraction, field
  derivation, source-image rerender, import replay, truncation handling and
  rejection of mutated source/overlapping output paths.
- Legacy named-AI environment: **34 passed**, with the public-main integration
  module skipped. Five local cases preserve ai add/list/probe/run, source hashes,
  prompts, image order, budgets, one load per batch, incomplete exit 3, device
  metadata, and formula-review holds. Its baseline commit is not published;
  this is explicitly a local compatibility claim.
- MCP tests use an actual stdio client to initialize, discover and invoke both
  run and run_batch. CLI interrupt returns cancelled/130 and reaps the worker.
- Receipt replay is independent of caller acknowledgement. Tests kill a parent
  during item two, preserve item one and the live worker's inherited lease, then
  retry only item two. An external worker writes timeout quarantine even after
  its parent dies. External servers are never stopped by the runner.
- Runtime/cache identity includes Python, relevant MLX/transformer versions,
  Ollama version and the transport implementation hash. Ollama model identity
  and local capabilities are checked before input and after generation.
- Separate integrity-checked settlements record worker reaping, closed lease
  handles and external termination acknowledgement. A missing settlement does
  not imply cleanup. Results and settlements never grant domain acceptance.
- Real MLX: Qwen3-VL-8B read a generated 42 twice in a warm worker; receipt replay
  reused the first item. The published PDF2Data adapter also read Code: 42 END
  from a generated PDF and reverified all native source files unchanged.
- Real Ollama: Qwen3 8B answered 6 + 7 and identified the exact faulty line in a
  synthetic invoice function. The parent checked the quote/replacement and ran
  the corrected function's assertion. The dedicated test server was unloaded
  and stopped by its test host, not by AskMill.
- The executable, skill and local qwen profile are installed on the development
  host. That profile uses the existing shared GPU locks and leaves PDF2Data's
  configuration unchanged.
- Build, source and wheel evidence is recorded in
  [validation-2026-11-01.json](validation-2026-11-01.json).
  [Completion audit](COMPLETION_AUDIT.md) maps the objective to concrete checks.

The initial implementation exposed shutdown-response redirection, a cleanup
race, lost device metadata and a test fixture import issue. These were corrected
before qualification. The first native hardware verifier used a relative path
where the consumer requires an absolute path; the corrected verifier passed.

Release code revision `503c2fac22a84a7ab5be1a33a1bd12ab90daf6a5`
passed [CI run 41287184550](https://github.com/rudraptpsingh/askmill/actions/runs/41287184550):
29 core tests on Python 3.10, 3.12 and 3.13, plus four published PDF2Data
integration cases. A fresh wheel-only environment separately passed 29 core
tests, then 33 after installing the pinned public consumer. That environment
imports AskMill from site-packages, not the checkout.

## Supported integration and remaining gates

Read [pdf2data.md](pdf2data.md) for exact consumer revisions and commands.

The qualified alpha is a POSIX local runner with external Ollama and owned MLX
workers. OpenAI-compatible profiles are explicitly unsupported until attested;
no hosted fallback or model downloads occur. Remote endpoint attestation,
Windows, owned Ollama lifecycle, memory admission, queue fairness, multi-user
authorization and full host-death recovery are future qualification work.

PDF2Data's public field-witness import stays operator-imported and unapproved.
Its default replacement and Query's existing owned-server/lease boundary have
not been migrated. Those rollouts need owner-specific parity, bilingual/corpus
and held-out source cases. Do not nest AskMill lease acquisition beneath an
existing caller-held device lease.

Installed CLI/SDK/MCP and skill behavior are tested. Two new Codex chats and a
matched end-to-end speed comparison have not been run; no speedup percentage or
legal/document-accuracy claim follows from the smoke cases.

## Continuation

The initial runner objective can close after the release checks and completion
audit pass. Subsequent consumer-default or hardware/product expansion should
take the corresponding gate above, preserve its owner checks, and record the
tested runtime/model/revision. Keep private inputs, host profiles and raw
receipts out of this repository.


## a3 model configuration update

The user's public-research selection is implemented in profile v2, with explicit
reasoning/sampling/context controls and model-aware MLX templates. Selected host
roles use Qwen3.5 9B for coding, Gemma 4 E4B for general/visual work and PaddleOCR
for document recognition. This supersedes the proposed new local benchmark
campaign, not the consumers' source acceptance checks.

Eight regression cases were added; expected suite totals are 37 core, 41 with
published PDF2Data, and 42 with the local legacy consumer. The staged v2 registry
is promoted only after the a3 installed executable checks it. This resolves
the router's observed a2 executable/v2 profile mismatch. a2 profiles and package
bytes remain available; other consumer adoption is pending explicit pin updates.

See releases/v0.1.0a3.md, MODEL_SELECTION_2026-11-01.md and the sanitized smoke
summary. Main, immutable package checksums, CI and host installed-use evidence
are recorded in the release assets.

## a4 structured-output contract

The routed consumer issue is confirmed: native Ollama `format` forwarding was
absent. Explicit request/result/batch v2 now supports a versioned, SHA256-pinned,
bounded response schema through the existing worker/leases. Local validation is
offline and independent of source or semantic acceptance. Failed and truncated
outputs are retained, receipt v2 includes the raw provider response, and cache
identity pins schema plus validator/runtime/transport implementation.

The initial 28 structured regression cases and all existing checks passed:
70 passed, one optional skip with the local legacy consumer installed. The
consumer's currently exported response schema passes the supported-subset
check. New tests include actual stdio MCP v2, CLI exits 0/3/4, invalid-output
replay and rejection before source image reads for unsupported providers.
The original v1 schema files and installed default launcher remain unchanged.
See releases/v0.1.0a4.md for the phase gates; package/main/release evidence is
recorded only after those gates pass. Consumer readoption is pending its owner.

Final source checks pass: **72 passed, one optional skip**, including 30 new
structured-output cases and the local legacy integration. A clean wheel-only
environment passes **67 core checks**, with both optional consumer modules
skipped before installing PDF2Data. Exported v2 schemas are validated against
actual requests/results from both source and installed package data.
An installed-wheel Gemma 4 E4B smoke returned the expected synthetic condition
source ID with a valid pinned schema, replayed correctly and recorded worker
reaping/acknowledged settlement without quarantine. This is a transport smoke,
not document-corpus or semantic-extractor acceptance. The installed default
remains a3; PDF2Data pins and existing jobs are unchanged.

## Installed a4 producer-adoption fixture

Historical transport evidence only. The later real-source-only user correction
supersedes this fixture as a current adoption deliverable. Preserve its original
receipts; exclude its six cases, canned outputs and synthetic model smokes from
current real-document coverage, accuracy, client eligibility and acceptance.
Current demos/evaluations must use actual sources and extracted records, with
the existing authorized customer profile and its review state preserved.

`examples/structured-source-id` provides one complete request and an executable
integration fixture for the released a4 CLI. Against the checksum-pinned,
noneditable installed wheel it passes six cases plus success replay: completion,
schema-invalid output, malformed/valid-JSON truncation, unsupported schema and
bad schema pin. Four synthetic HTTP-stub generation calls are made; replay and
request rejections add none. Actual raw outputs, schema/cache/receipt integrity
and acknowledged worker cleanup are retained in the private execution folder.
The fixture uses no model inference or real GPU leases and changes no producer,
profile, engine or release. The README gives exact CLI, SDK result and receipt
paths, and keeps schema validity separate from PDF2Data's source acceptance.

## a5 input/replay gate correction

The real-request audit confirmed four routed defects: duplicate raw JSON keys,
duplicate source IDs, missing aggregate source/input bounds and incomplete
cached-result cross-bindings. a5 adds strict bounded JSON decoding and source
limits, cross-binds result/raw response/model/runtime/attempt/session/settlement,
and emits settlement v2 with runner/profile/lease hashes. Source/customer review
states and externally owned permissions remain consumer gates.

29 controls over the actual request/receipt passed with zero model calls and
unchanged original bytes. The first metadata-budget control was below its
intended size; that failed harness attempt is preserved and the corrected
control reaches the configured cap. The historical parent-crash software check
exposed its prior assumption that a result without settlement could replay;
the regression now requires rejection while preserving that committed item.
Versioned schema/artifact pins and final checks are recorded in the a5 release
assets. Performance thresholds remain not_established.

The real-source question-proposal workflow is documented in
QUESTION_PROPOSALS.md. Its private CERC request/schema example is prepared and
contract-validated without dispatch or new answer/accuracy cases. The existing
deeper20 real-intent suite remains the first consumer suite.

The final source suite passes 83 software/metadata/real-envelope checks with
one optional integration skipped when the authorized real receipt is supplied.
The real receipt is external to this repository; CI without that input skips
those eight controls explicitly. These totals are not document accuracy cases.
The final expanded real-envelope control packet has 32 passing cases, including
strict settlement fields and runner/profile/lease binding. New model calls: zero.

## a6 MCP parity correction

The actual installed-a5 owner probe identified a single-call source-metadata
gap and SDK/application version ambiguity. a6 adds versioned `run_request_v1`,
closed/byte-bounded tool arguments and distinct initialize/producer-resource
identity through the existing Request/Session path. `run_batch` retains its
prior full-request support; no model/lease/receipt engine is duplicated.

The unchanged actual CERC request reaches a non-inference Session guard through
both full-request and batch tools. Eight refusal controls reject before any
session; no provider response is mocked. Initialize and resource identity checks
pass over actual stdio. The source suite passes 86 checks, one optional skip,
with the external authorized real inputs. These are controls, not accuracy cases.
SDK 1.12 with current Pydantic failed import; the optional MCP dependency floor
is now the qualified 1.30 series and the isolated probe passes after upgrade.
Final installed-wheel/main/release checks are recorded in the a6 release assets.
Live generation/cache adoption and source/client approval remain pending their
separate consumer gates.

## Execution-mode lessons from real consumers

Reviewed the real completed/incomplete CERC generation receipts, acknowledged
settlements, isolated CLI/MCP admission controls and Query's real deterministic
source-only qualification. The demonstrated gap was guidance: a cap, a generic
structured port call, zero fresh inference and zero runner initialization were
being discussed as interchangeable. Session replay still acquires leases and
performs runtime checks; a cache miss can dispatch inference. CLI/MCP refusals
before Session need caller-retained error artifacts, not an invented model
receipt. EXECUTION_MODES.md now states those boundaries, replay settlement
binding and separate scope/domain/performance gates.

No new owning engine defect was demonstrated. The qualified a6 release,
schemas, device leases, frozen failures and consumer/runtime pins are retained.
This guidance update performs no inference, warmup or new query runs; current
Query source_rules_only remains without an initialized AI runner. Private
evidence pins and selective read-only checks are kept outside the public repo.
Selective verification rechecked two real result/settlement pairs, the three
existing source-only rows sharing one original/page, caller-retained CLI/MCP
refusals, 22 relative documentation links and bounded-load equivalence for the
actual request. Provider/runner guards observed zero calls/initializations;
these repeated inspections add no new source or answer accuracy cases.

## Offline capacity evidence, 2 November 2026

Added the repository-only capacity_preflight.py utility and CAPACITY_PREFLIGHT.md.
It validates a frozen request against a separately pinned installed wheel and
records profile/manifest/template identities, byte counts, output reservation
and unknown tokenization/capacity. No runner/CLI/MCP engine behavior changes and
no new inference release or consumer default migration are required.

Eight focused offline software controls pass, including metadata refusal before
weight-container access and unchanged input checks. Ruff passes for the utility
and focused tests. Separately, an actual repaired consumer request passes the
immutable a6 validator with a declared 8192 context and 2048 output reservation;
6144 is arithmetic only, with no exact token count or fit claim. A private audit
hook observed no network/model/lease/weight operations and no runner import;
request, registry, manifest, execution reference, wheel and utility hashes stayed
unchanged. The older unsupported-pattern descriptor and its refusal evidence
remain frozen. Caller-owned post-validation, execution authorization, source
semantics, identity/scope, performance and capacity gates remain independent.
This repeated inspection adds no source/document accuracy case.

## Capacity investigation follow-up, 2 November 2026

Reviewed the retained unsupported-pattern refusal and the repaired real request
before changing the helper. Public source research identified the built-in
Qwen3.5 renderer, including non-thinking framing, and a render-only provider
route that still schedules a runner. That route was not called. Cached
Qwen3-VL assets cannot qualify the selected Qwen3.5 container; no revision-bound
standalone tokenizer export/equivalence evidence is present. Tokenization and
context fit remain unknown, with no numerical bound invented.

The repository helper now identifies missing tokenizer/rendering and capacity
dependencies in its report. Added two affected-stage software regressions:
unsupported pattern grammar preserves its input, and fewer prompt bytes with a
declared output budget still cannot produce a capacity pass. Ten focused offline
controls and lint/format pass. The exact old rejected request and repaired real
request are rechecked under weight/network/lease guards in private evidence;
no new source/document accuracy cases or inference are introduced. Canonical
caller postvalidation and existing execution/profile pins remain unchanged.
The diagnostics are distributed separately as a tool-only immutable release;
a6 inference behavior and the global launcher stay unchanged. Consumer adoption
of the helper remains explicit and pending its owner.

## Separate metadata and qualified-upstream static stage, 2 November 2026

The expressly authorized next stage preserves the original no-container-read
reports and accounts full existing-container hash I/O separately. A bounded
GGUF scanner exports unchanged metadata fields into a zero-tensor sidecar;
the maintained pinned llama.cpp parser/tokenizer loads only that vocabulary,
with GPU backends disabled and no context or inference. The native CPU driver
was compiled after detecting an incompatible pre-existing x86-only library.
That library/service was not changed. Tokenizer and renderer setup fetch only
public code/toolchains/runtime assets, never weights or consumer data uploads.

A compiled driver now invokes the pinned upstream Ollama renderer directly.
The independently downloaded official provider executable matches the installed
binary byte-for-byte and also contains the dirty marker; it is not evidence of
a local modification. A clean source build was completed before this identity
was resolved, then retained unused. The accepted plan direction uses the verified
publisher executable and qualified-upstream static evidence; no functional
renderer difference has been demonstrated and source-to-binary correspondence
remains explicitly unproved.

The private candidate keeps the exact model weights and source/prompt/schema
contents, while explicitly proposing a new named profile/context/output budget.
The old declared-budget candidate overflows for the upstream renderer; the new
candidate fits its declared static limit. Actual provider prompt_eval_count,
runtime allocation, finish/completeness and settlement remain fresh-execution
gates. No provider has been started and no execution is authorized. A macOS OS
sandbox denies network/original-container/lease access during the three CPU
helper invocations. Old requests/reports/global profile and launch configuration
hashes remain unchanged. Twenty affected-stage local software controls pass,
including the native helper's pre-load tensor-container refusal; pure Python
lint/format and native Go/C++ compilation pass. Accuracy cases added: zero.

## P0 bounded-model tracker alignment, 2 November 2026

Recorded producer-side alignment in TRACKER_ALIGNMENT.md after reading the
hash-pinned programme/research and the golden tracker ledger README/generator.
The existing run_request_v1 wrapper remains closed; authority/capacity/review
and ledger binding live outside the tool arguments. The proposed document/run
mapping separates extraction/model time, observed/reserved tokens, cache reuse,
transport completion and caller-owned acceptance/rejection. Original-document
and multi-document deduplication remain explicit.

A concrete Map-owned interface decision remains: current document-run v1 has
no typed AskMill token/review/history stage, and its fixed pipeline drops that
stage from generated tracker output. No unagreed ledger row or adapter is
written. P0 is contract alignment only, not coverage/accuracy progress. No new
model run, download, default/profile/lease change, prior receipt edit, runtime
schema change, CI rerun or release is performed. P3/P4 tasks stay gated. Local
qualification checks document links and the unchanged closed MCP/schema pins;
consumer/Map acceptance of the proposed extension remains pending.

## P0 retained-invocation reporter qualification

Map 0.37 intake 1.1 resolves the initial stage/history interface gap. Added a
separately versioned CPU-only reporting CLI because native AskMill receipts are
not document-run intake records and cannot be submitted as metadata-only rows.
The emitter reopens original subject proofs, exact frozen prompt JSON source
bindings, native envelope/cache identity, observed counters, replay and caller
review evidence. It preserves null unknowns and rejects a reader-context PDF
absent from the actual model input. It never initializes Session or leases.

Twenty focused retained-source/adversarial software controls pass, including
installed Map multi-PDF invocation dedup/conflict checks, replay counter/cleanup
controls and receipt-bound caller review. Real retained complete and failed-CLI
records validate through the downloaded Map 0.37 wheel/final requirements;
local append inserts two events for one original and identical replay inserts
zero. Local batch registration succeeds; owner/golden registration remains its
own receipt. No new inference, source parsing, defaults/global consumer repin,
CI run or accuracy case is introduced. P3/P4 remain gated. Tool-only release
and installed adapter qualification are required before consumer adoption.

## Offline report receipt boundary

Added a separately packaged `report_receipt_gate.py` for text-only Ollama v2
retained report-phase receipts. It checks native input/settlement bindings and
adds raw assistant, stop, tool-call, stdout and expected lease-count gates;
source completeness, fit, trusted origin and domain acceptance remain host
gates. With an existing private real receipt and explicitly mutated offline
controls, `tests/test_report_receipt_gate.py tests/test_json_gates.py` passed
17 tests; no new inference or provider/service operation was performed. The
consumer must pin its installed artifact and separately establish source, fit,
authorization and actual report execution; this does not qualify R1.

## Report host orchestration boundary

Added a default-closed opt-in phase orchestration SDK with host-supplied policy,
durable journal, provider and independently pinned receipt gate. Six synthetic
controls passed for closed/unknown-fit refusal, exact frozen request, one attempt,
uncertain interruption and receipt refusal. These callbacks prove software flow,
not real provider, fit, source authorization or consumer acceptance. The
existing pinned Qwen vocabulary-only static toolchain counted the exact Query
alpha20 generation/review probes without inference: 3721/4040/22481 input tokens
for generation/one/eight paragraph review; 4096 output tokens reserved. On its
16384-context candidate the eight-paragraph probe exceeds by 10193. Source-to-
binary identity and live allocation are not attested; R1 remains closed.

## Report host manifest aliasing correction

Independent review found v0.1.0 can complete a phase with a different receipt
if a shared provider manifest changes while the receipt gate is starting. Do
not adopt that release. v0.1.1 detaches the manifest, binds receipt/session
identity and phase pins across the gate, refuses gate mutation, and detaches
journal and caller completion results. A synchronized cache-refresh regression
uses two synthetic native receipts and the actual receipt gate. Together with
existing receipt and orchestration controls, 27 tests passed with one retained
real receipt; no inference. Independent re-review and Backend acceptance are
pending. Historical release/tag and previous evidence are preserved.

## Embedding bridge candidate

Added a separately packaged explicit registered-encoder CLI/SDK over Query's
existing pinned EmbeddingGemma2 host; it does not change the global AskMill
registry or inference runtime. It requires a separately authenticated host
SOURCE_READ gate, current resource policy, pinned adapter/dependencies/profile,
exact 1–32 text hashes, observed token counts and validated normalized float32
rows, plus host cleanup confirmation. Nine synthetic/offline controls passed;
no actual source, provider or model was used. The Query host sends an additional
empty-input `/api/embed` cleanup request; its budget accounting remains pending.
Actual B1 profile/grant/resource and isolated consumer acceptance are required.

The revised embedding bridge v0.1.1 accounts for the explicit smoke limit:
one actual embedding data request plus one owned-service cleanup request. It
requires exactly two successful `/api/embed` entries in the fresh owned-server
log and pins the log; the native receipt separately records one model data call.
A synthetic extra-request refusal control brings the offline suite to ten tests.
Host-owned source authorization and acceptance remain pending; no encoding ran.

## Query embedding-batch typed contract inspection

Added a non-dispatching inspector for Query's exact pinned request/response
schemas, kept external because Query declares its package UNLICENSED. It checks
schema, file-byte versus canonical model-profile pins, scoped row identity,
float32 vector hash/normalization, and four receipt file hashes while leaving
source authority and receipt origins unverified. Six synthetic controls passed
with the consumer's pinned schemas; actual model-profile canonical digests were
independently reproduced offline. Existing bridge v0.1.1's historical Query
resource guard does not admit the new B1 source or separate phase plan. The new
B1 guard, live source checks, typed execution integration and Query consumer
acceptance remain open; no actual encoding was attempted.
