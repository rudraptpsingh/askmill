# Model selection and qualification plan

Date: 1 November 2026. This was the original comparison proposal. The user
subsequently requested selection from public research and actual configuration;
MODEL_SELECTION_2026-11-01.md records the implemented decision and supersedes
the proposed local comparison campaign below.

## Reference host and configuration

The reviewed host is an Apple M5 Max with 36 GB unified memory, 18 CPU cores
and 32 GPU cores. About 651 GiB disk space was free. Working-set memory and
context, rather than disk capacity, constrain candidate selection. Weight
size is not the total inference memory requirement.

Runtimes: Ollama 0.40.13, MLX 0.32.4, mlx-vlm 0.7.11, Transformers 5.21.0.
The MLX environment contains Qwen3.5, Gemma 4 and PaddleOCR architecture modules.
This inventory does not prove candidate/runtime compatibility.

Only the qwen MLX Qwen3-VL-8B profile is registered in AskMill; cached weights
occupy about 5.37 GiB. Keep its digest/runtime as the vision baseline. Other
models are cached outside that registry:

- Primary Ollama store: qwen3:4b, 4b-instruct, 8b, 14b and gemma3:27b.
- Secondary Ollama store: gemma4:e2b, gemma4:e4b and embeddinggemma-2:270m.
- Vision: PaddleOCR-VL-1.5 4-bit (about 0.66 GiB weights) and Granite Docling
  258M MLX (about 0.59 GiB).

A model in the second store needs a service configured for that store; it is
not visible to a server using the first store. No Ollama service answered the
version probe. AskMill uses externally managed Ollama services. Keep existing
shared GPU locks and distinguish local profiles from downloaded files.

## Existing task evidence

Small downstream source-bound evaluations found qwen3:4b-instruct had 5/6
strict ingestion passes, versus 2/6 for qwen3:8b and 1/6 for gemma4:e4b.
On 12 legal cases, qwen3:8b and gemma4:e4b each had eight strict passes,
versus seven for qwen3:14b. Gemma3:27b was not run because its earlier memory
check could not accommodate weights, context and reserve.

These are frozen downstream cases, not general coding benchmarks. Newer or
larger models are candidates, not established improvements. Retest per role.
Private host inventory and domain fixtures stay local.

## Selection policy

The user's preference is model-agnostic selection. Choose the model and runtime
per use case using verified quality, latency and memory, with no preferred family.
Qwen is an existing baseline, not a requirement or automatic first download.
Use cached models to reduce setup cost, then shortlist cross-family challengers.
The selected role may keep a small specialist while another role uses a larger
general model. If one model wins several roles, reuse it.

## Candidates by task

| Task | Candidate families | Comparison that matters |
|---|---|---|
| Coding, failing tests and bounded patch review | Devstral Small 2 24B, Qwen compact models, Gemma 4 | Correct source location, executable fix, regression tests and review time |
| Reasoning and source-bound structured answers | GPT-OSS 20B, Gemma 4, Ministral 3 8B/14B, Qwen | Evidence coverage, correct source IDs, contradictions, missing facts, schema and substantive correctness |
| OCR, tables and formula transcription | PaddleOCR-VL, Qwen-VL, Gemma vision | Exact literals, units, operators, Hindi qualifiers, reading order and crop/page binding |
| Document structure | Granite Docling plus PDF2Data's native/layout pipeline | Structural fidelity, reading order and retention of original evidence; qualify task-specific output first |

Devstral Small 2 is a coding-focused 24B candidate. GPT-OSS 20B is a reasoning
candidate; its Ollama distribution is about 14 GB. Ministral 3 provides another
compact family to compare. These new downloads remain unqualified on this host,
and a 24B coding model also needs admission checks. Publisher benchmarks nominate
candidates; our frozen tasks choose the winner.

## Acquisition order

| Order | Candidate | Proposed role | Status / decision |
|---|---|---|---|
| Baseline | Existing Qwen3 8B and Qwen3-VL 8B | Text and vision controls | Cached; preserve current behavior |
| First | qwen3:4b-instruct, qwen3:14b, gemma4:e4b | Fast classification; code/reasoning alternatives; independent vision candidate | Already cached; compare real task quality |
| First | PaddleOCR-VL-1.5 4-bit | Specialist OCR, tables and formula transcription | Cached; qualify task prompts, template and PDF2Data evidence checks |
| Candidate pool | Devstral Small 2 24B, GPT-OSS 20B, Ministral 3 8B/14B, qwen3.5:9b | Coding, reasoning and compact general challengers | Select by task and memory; no automatic first download. Pin exact runtime, quantization and digest |
| Conditional | qwen3.8:27b | Slower quality-oriented challenger | New download; library lists about 18 GB; admit only with measured memory/context reserve |
| Deferred | qwen3-coder-next | Larger coding model | Q4 variant about 52 GB, above total host memory; low active parameter count does not make weights fit |

For each workload choose a small useful shortlist, rather than download every
generation. Qwen3.8 remains one conditional 27B candidate, with no priority over
a better-fitting cross-family model. None of the new candidates is a measured
winner on this host.

Primary sources:
- [Devstral Small 2 publisher announcement](https://mistral.ai/news/devstral-2-vibe-cli/)
- [GPT-OSS 20B distribution](https://ollama.com/library/gpt-oss:20b)
- [Ministral 3 variants](https://ollama.com/library/ministral-3/tags)
- [Runtime-specific thinking controls](https://docs.ollama.com/capabilities/thinking)
- [Qwen3.5 variants](https://ollama.com/library/qwen3.5)
- [Qwen3.5 9B model card](https://huggingface.co/Qwen/Qwen3.5-9B)
- [Qwen3.8 variants and size](https://ollama.com/library/qwen3.8)
- [Qwen3.8 27B model card](https://huggingface.co/Qwen/Qwen3.8-27B)
- [Google Gemma 4 Ollama setup](https://ai.google.dev/gemma/docs/integrations/ollama)
- [PaddleOCR-VL-1.5 model card](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.5)
- [PaddleOCR MLX conversion](https://huggingface.co/mlx-community/PaddleOCR-VL-1.5-4bit)
- [Qwen3-Coder-Next size](https://ollama.com/library/qwen3-coder-next)

## Configuration work before comparing models

AskMill currently hard-codes Ollama thinking off and temperature zero, and does
not expose num_ctx. Its MLX transport uses a generic processor template. Different families need distinct controls: GPT-OSS uses reasoning effort;
Qwen/Gemma have their own supported thinking settings. A universal thinking-off
request is not a valid policy for every model. PaddleOCR uses
task prompts such as OCR:, Table Recognition: and Formula Recognition:.

Add typed, bounded per-profile settings for thinking, context, sampling and
image preprocessing/template mode. Record resolved settings in execution
identity and receipts; changes must invalidate cache. Preserve old defaults.
Start bounded trials at explicit 8K context, then test 16K where needed.
These are trial budgets, not a claim that advertised maximum contexts fit
or publisher benchmark results transfer.

Add cached-model registration/probing using live Ollama digests and
capabilities; describe the service/store explicitly. Check new architecture
and quantization support in an isolated runtime if required. Do not upgrade
another component's runtime in place.

Before the conditional 27B trial, add memory admission/telemetry covering
warm services, image tokens and KV cache, with an initial proposed 8 GiB
system reserve. This is a policy to validate, not a measured requirement.
Postpone a trial if another owner's warm model consumes the reserve.

## Five phases

| Phase | Goal / work | Required outcome |
|---|---|---|
| 1. Freeze baselines | Pin profiles, models and runtimes; capture representative failures and settings | Reproducible inventory and unchanged baseline receipt |
| 2. Qualify configuration | Typed settings, templates/prompts, context guards, registration and memory checks | Tests prove settings reach both runtimes, change cache identity, retain incomplete output and preserve profiles/leases |
| 3. Compare cached models | 20 coding/log cases, 20 Hindi/English/formula/table crops, 20 source-selection/JSON cases; reserve five per category as held-out | Per-task quality/failure, cold/warm latency and peak-memory report without new weights |
| 4. Trial targeted downloads | Shortlist by task across Devstral, GPT-OSS, Ministral, Gemma, Qwen and OCR specialists; run admitted candidates on the same frozen cases | Evidence of improvements within explicit latency/memory budgets |
| 5. Promote by role | Held-out checks and three repeats for finalists; consumer source/citation/compatibility checks | Versioned dev-fast, dev-quality, pdf-read and pdf-ocr-specialist profiles, rollback, support matrix and one Central Router handoff |

Proposed promotion gate: no regression on critical cases, plus two additional
verified passes on the 15-case development set, or equal quality with materially
less reviewed end-to-end time. A quality-oriented candidate may have a declared
slower latency budget. Do not tune on the five held-out cases. If evidence is
tied or noisy, keep the baseline or expand the test set.

Freeze evidence bytes, crop/DPI, prompt version, output contract and input
coverage. Report backend preprocessing differences. Give reasoning modes
separate bounded budgets. Measure verified fixes/readings, not just tokens/sec
or valid JSON. Reject silent truncation and retain local-only behavior.

Domain fixtures and grading remain with PDF2Data, Query, Map and Impact.
AskMill owns invocation, receipts and resource coordination. An embedding
change is a separate index migration; equal vector dimensions do not make
models interchangeable. Audio, embeddings and autonomous tool execution are
not current AskMill operations.
