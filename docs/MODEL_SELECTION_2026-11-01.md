# Research-based model selection

Decision: 1 November 2026. The user requested selection from public studies
and actual use, rather than a new 60-case local comparison campaign.

## Selected roles

| Profile | Model | Use | Selected configuration |
|---|---|---|---|
| dev-code | Qwen3.5 9B Q4_K_M | Bounded coding, logs and patch suggestions | Direct response, 8K context, temperature 0.7, top-p 0.8 |
| dev-code-reason | Same Qwen3.5 weights | Harder reasoning over selected code | Thinking enabled, 8K context, temperature 0.6, top-p 0.95 |
| general | Gemma 4 E4B | General analysis and structured source questions | Thinking enabled, 8K context, temperature 0.7 |
| vision-review | Same Gemma 4 weights | Additional visual reading | Thinking disabled, 8K context, temperature 0 |
| pdf-ocr / pdf-table / pdf-formula | PaddleOCR-VL-1.5 4-bit | Literal OCR, table or formula transcription | MLX model-aware template, temperature 0; prompts OCR:, Table Recognition:, Formula Recognition: |
| qwen | Existing Qwen3-VL 8B | Prior pinned work and baseline | Existing v1 configuration preserved |

Profiles sharing weights do not consume a second model download. They are host
configuration, not hard-coded routing in the library. Source acceptance remains
with the caller.

## Public evidence and reasoning

- **Coding:** Qwen's published 9B model card reports 65.6 on LiveCodeBench v6
  and documents distinct thinking/non-thinking modes. Its approximately 6.55 GB
  Q4 distribution leaves more working memory on this 36 GB desktop than the
  15 GB Devstral Small 2 or approximately 18 GB Qwen3.8 27B distributions.
  This is a practical quality/resource decision, not a claim that 9B wins
  every coding benchmark.
  [Qwen model card](https://huggingface.co/Qwen/Qwen3.5-9B),
  [exact distribution](https://ollama.com/library/qwen3.5:9b-q4_K_M).
- **General analysis / visual review:** Gemma 4's technical report and Google
  model card describe efficient multimodal reasoning, coding and multilingual
  capabilities. E4B was already cached and provides a second model family
  without another download.
  [Technical report](https://arxiv.org/abs/2607.02770),
  [Google model card](https://huggingface.co/google/gemma-4-E4B-it).
- **Document recognition:** PaddleOCR-VL-1.5's paper reports 94.5% on
  OmniDocBench v1.5 using a 0.9B model, with robustness tests on scanning, skew,
  warping, photography and illumination. Its specialized task interface and
  small cached MLX conversion make it the chosen transcription specialist.
  [Paper](https://arxiv.org/abs/2601.21957),
  [task prompts](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.5),
  [MLX conversion](https://huggingface.co/mlx-community/PaddleOCR-VL-1.5-4bit).
- Devstral Small 2's publisher reports 68.0% SWE-bench Verified. That agent
  benchmark is different from LiveCodeBench; the scores are not a direct
  ranking. The larger footprint makes it an optional future quality profile
  rather than this busy host's daily default.
  [Publisher evaluation](https://mistral.ai/news/devstral-2-vibe-cli/).

The reports are primary/publisher evaluations, not an independent matched
head-to-head study of these exact local quantizations. We use them to decide.
Local checks establish integration, not a new accuracy ranking or legal
reliability. Future domain acceptance is still owned by PDF2Data/Query/Map/Impact.

## Installation and storage

The exact Qwen3.5 Q4 tag was downloaded and pinned from the local Ollama API.
Gemma's existing content-addressed blobs were hard-linked into a dedicated
AskMill store; the prior store remains unchanged. Paddle's existing MLX snapshot
is reused without copying weights.

Selected model files: roughly 6.6 GB Qwen, 9.5 GB Gemma and 0.7 GB Paddle,
about 16.8 GB total. New model data is roughly 6.6 GB, plus a small runtime
bundle. This excludes prior baseline models retained for reproducibility.
Inference RAM also includes context, image processing and temporary buffers.

The dedicated loopback Ollama service uses one loaded model and one parallel
request, 8K default context and a 30-second idle keep-alive. Cloud execution is
disabled in the service and rejected by AskMill's model probe. It is an external
service from the runner's perspective; the runner does not stop/unload it.

A portable Ollama installation needs its complete runtime bundle, including
llama-server, libraries and Metal backends. Copying only its CLI binary can
start an API server yet fail generation. Our first setup exposed that error;
the complete bundle and GPU runtime were then installed before repeating use.

## Local integration observations

Actual calls used the existing shared host leases and pinned model/runtime IDs:
- Paddle read the generated 42 and the published PDF2Data source-bound field
  case; original artifacts and approval flags stayed unchanged. The generic
  transcription prompt initially duplicated a line; the explicit OCR: prompt
  returned the literal once and is retained in the consumer reading bundle.
- Gemma returned the correct task order ABC.
- Qwen identified the exact faulty invoice-function line and replacement.
  The optional reasoning mode generated 2,639 tokens and took about 48 seconds
  on this tiny case. Direct mode returned the same correct repair in about
  2.3 seconds. These are individual smoke observations, not throughput averages
  or a general speedup claim. Routine code triage therefore uses direct mode.

Receipts stay local; sanitized integration summaries are published with the
release evidence. No existing consumer pin is silently migrated.
