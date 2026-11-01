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
