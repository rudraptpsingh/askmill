# Qwen3.5 offline static qualification

This is a separately authorized stage after the no-container-read
[capacity evidence utility](CAPACITY_PREFLIGHT.md). It qualifies a pinned
upstream renderer and an exact container's tokenizer metadata. It does not
attest a running provider, allocate a model context or authorize inference.
The original frozen request, profile and prior unknown-capacity receipt remain
unchanged. Prepare new candidate files and obtain explicit consumer acceptance.

## Stages and artifacts

1. **Export metadata and identify the container.** `gguf_metadata_export.py`
   scans at most 64 MiB of GGUF v2/v3 metadata and stream-hashes the entire
   existing container against its expected digest. It exports the same metadata
   field bytes into a private zero-tensor GGUF sidecar. Its receipt explicitly
   records both metadata bytes read and all container bytes read for hashing.
   It never copies tensor payload into the sidecar. This stage does read a
   weight container; it must never be presented as the earlier no-weight-read
   preflight. No weights are loaded into a tensor model.
2. **Build the maintained CPU tokenizer.** Pin the llama.cpp source commit and
   build with GPU backends disabled. Compile `gguf_tokenize.cpp` against that
   exact native library/header pair. The driver refuses tensor-bearing input,
   supplies an empty GPU-device list, uses `vocab_only`, and never initializes a
   backend, context, Session or inference. Maintained llama.cpp validates/parses
   the exported GGUF. Pin the driver binary, source and every linked library.
3. **Build the maintained renderer driver.** Build `qwen35_render.go` from the
   pinned Ollama module checkout. It imports Ollama's actual renderer directly,
   rather than implementing another template. Scope is one user text message,
   thinking false, no images/tools/model-system/history layers. Unknown layers
   are refused by the static checker. Pin source checkout, toolchain and binary.
4. **Identify a staged provider without starting it.** Verify the official
   release archive's independent published checksum and exact executable hash.
   Record the provider build/version and renderer-source commit. An official
   artifact can itself contain a dirty build marker; that marker alone does
   not establish a local modification or functional renderer difference.
   Publisher binary identity is useful engineering evidence, while direct
   source-to-binary correspondence remains explicitly unproved. Do not rebuild
   a whole provider merely to erase that marker.
5. **Qualify the new candidate.** The static checker verifies all plan/input/
   wheel/program/sidecar pins, validates the Request with the separate a6
   installation, and binds the sidecar export to the profile's original model
   manifest/container digest. It runs only the pinned renderer/tokenizer helpers
   in a macOS OS sandbox that denies networking and original-container/lease
   access. It records token counts with and without automatic special tokens.
   Native context, declared profile context and reserved output remain distinct.

Setup may fetch pinned public source, toolchains and provider binaries; it must
not fetch model weights or upload consumer data. Counting reuses the sidecar and
performs no original-container read, network call or provider startup. Wrong
architecture libraries are not usable native tokenizer dependencies; build a
separate correct-architecture CPU helper without replacing another runtime.

## Commands and pinned dependencies

The qualified source pair is Ollama
`04088e7c9d41cba5d33bafbf788d87a465c79d5b` (v0.40.13) and llama.cpp
`39febd2adb947b70da35e95f9351b3bf58ad170a` (b11963), the version selected by that
Ollama commit's [LLAMA_CPP_VERSION](https://github.com/ollama/ollama/blob/04088e7c9d41cba5d33bafbf788d87a465c79d5b/LLAMA_CPP_VERSION).
Review the maintained [vocabulary-only interface](https://github.com/ggml-org/llama.cpp/blob/39febd2adb947b70da35e95f9351b3bf58ad170a/include/llama.h),
[model loading branch](https://github.com/ggml-org/llama.cpp/blob/39febd2adb947b70da35e95f9351b3bf58ad170a/src/llama.cpp)
and [tokenization endpoint flags](https://github.com/ggml-org/llama.cpp/blob/39febd2adb947b70da35e95f9351b3bf58ad170a/tools/server/server-context.cpp).

Use a separately installed AskMill a6 Python for the export/checker. Do not
upgrade a consumer's execution runtime or global launcher for these helpers.

```sh
/path/to/pinned-a6/bin/python tools/gguf_metadata_export.py \
  --container /path/to/existing/model-container \
  --expected-sha256 EXACT_CONTAINER_SHA256 \
  --output /path/to/private/new-export

cmake -S /path/to/pinned/llama.cpp -B /path/to/private/cpu-build \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON \
  -DGGML_METAL=OFF -DGGML_CUDA=OFF -DGGML_BLAS=OFF \
  -DGGML_OPENMP=OFF -DGGML_BACKEND_DL=OFF -DGGML_NATIVE=OFF \
  -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_TOOLS=OFF \
  -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=OFF \
  -DLLAMA_BUILD_COMMON=OFF -DLLAMA_CURL=OFF
cmake --build /path/to/private/cpu-build --target llama --parallel 6

clang++ -std=c++17 -O2 \
  -I /path/to/pinned/llama.cpp/include \
  -I /path/to/pinned/llama.cpp/ggml/include \
  tools/gguf_tokenize.cpp /path/to/private/cpu-build/bin/libllama.dylib \
  -Wl,-rpath,/path/to/private/cpu-build/bin \
  -o /path/to/private/gguf-tokenize-cpu
```

From the pinned Ollama checkout, compile the renderer driver using its pinned
Go toolchain and module checksums. The driver source stays outside that checkout:

```sh
CGO_ENABLED=0 GOTOOLCHAIN=local go build -trimpath -buildvcs=true \
  -o /path/to/private/qwen35-render /path/to/askmill/tools/qwen35_render.go
```

Prepare a caller-controlled `askmill.offline-toolchain-plan.v1` JSON artifact.
Every asset pin is `{path, sha256, bytes}`. Required assets are registry,
candidate_request, parent_frozen_request, wheel, original_model_manifest,
metadata_export, metadata_sidecar, provider_build, provider, renderer, tokenizer
and tokenizer_libraries. Also supply profile, blob_directory,
renderer_source_commit, tokenizer_source_commit and tokenizer_build_flags.
The pinned provider-build record must identify the independently verified
publisher binary and renderer-source commit; its llama_server asset is also
verified. Keep service ownership, shared leases and acceptance requirements
in the private plan. Plans are trusted local inputs pinned by the caller,
not signed attestations; protect their source and storage.

```sh
/path/to/pinned-a6/bin/python tools/qwen35_static_preflight.py \
  --plan /path/to/private/toolchain-plan.json \
  --plan-sha256 EXACT_PLAN_SHA256 \
  --output /path/to/private/new-qualification
```

The result contract is `askmill.qwen35-static-qualification.v1`. Its scope is
`qualified_upstream_renderer_static`. The complete rendered input count and
reserved output are compared with the smaller of the native and declared
context limits. This is a static arithmetic decision for that qualified
upstream renderer, not actual provider `prompt_eval_count`, allocation, memory
admission, output completeness, performance or domain approval. The checker
keeps source-to-binary correspondence unproved and execution unauthorized.
No result file or static fit may silently enable the candidate profile.

## Fresh execution acceptance

A new private named profile/loopback endpoint may reuse the pinned existing
weights through a private model store; do not alter another service/global
registry. An eventual supervised service must own and clean only its recorded
process. Use the existing shared device leases for any later model execution.
Do not start it while preparing this offline qualification.

The consumer must accept a fresh descriptor with exact executable/profile/
request/count/output pins and new bounded authority. On the eventual authorized
run, retain actual provider prompt_eval_count, requested/available allocation
and context evidence, output token count/finish reason, and acknowledged cleanup
settlement. Reject unexplained count mismatch, clipping, missing capacity
attestations or incomplete output before claim acceptance. Provider grammar
success does not replace canonical caller pattern checks or source semantics.

Public regressions are software boundary controls. Real consumer requests and
all model-derived metadata/token IDs remain private. Repeated tokenization is
not a new model response or document/source accuracy case.
