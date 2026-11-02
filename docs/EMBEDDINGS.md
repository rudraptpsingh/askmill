# Registered local embeddings

AskMill `0.1.0a7` adds an explicit `embedding_profiles` registry and `askmill embed` for one bounded local Ollama-owned embedding batch. Generation profiles and existing installations are unchanged; nothing is auto-registered or migrated. Install the separately pinned wheel with its `embedding` extra (`tokenizers` and `psutil`) in a new environment. `askmill list` shows the registered profile-file references in the selected configuration; it does not load a model.

An `embedding_profiles` entry maps a host-selected name to `{ "path": "/absolute/profile.json", "sha256": "<exact profile file bytes>" }`. `EmbeddingProfile` and `EmbeddingRequest` JSON schemas are packaged in `share/askmill/schemas`. The profile pins the local provider binary and all host-qualified runtime files, an already-cached model manifest/revision and model store, its bound tokenizer file, dimensions/context, an independently trusted context gate, exact existing shared lease paths, minimum available memory, maximum observed owned-process RSS and request timeout. The selected registry entry's canonical sorted compact UTF-8 JSON SHA is returned separately as `registry_entry_sha256`; `profile_sha256` is the exact profile-file byte SHA. The host must independently establish that its runtime-file inventory is complete and the profile and gate are authentic; a checksum alone is not a signature.

```sh
askmill --config /private/profiles.json list
askmill --config /private/profiles.json embed --profile chosen-encoder \
  --request /private/frozen-request.json --request-sha256 EXACT_FILE_SHA256 \
  --output /private/new-attempt-directory
```

The CLI's configured/repeated `--lease` paths must exactly match the embedding profile. A request `askmill.embedding-batch.v1` contains `batch_id`, an opaque host-owned `scope_sha256`, and 1–32 ordered `{id, text, sha256}` rows. Text hashes are SHA256 over exact UTF-8 bytes. The caller supplies complete model-ready inputs and any task-specific prefixes; AskMill never inserts a prefix, chunks, clips or silently truncates. A pinned offline tokenizer runs with truncation disabled, and each token count must fit the configured context. The provider receives `truncate:false`; the observed aggregate provider token count must equal the tokenizer total and `/api/ps` must report the requested actual context allocation. This establishes only these observed properties for this run, not semantic or source quality.

## Host context and budget gate

The independently authenticated profile's pinned Python `context_gate` is trusted executable host code. It supplies:

* `authorize(profile, request, stage) -> bool`, called with `before`, `before_dispatch`, and `after`. The host must validate the opaque scope, current principal/access and revocation state; return exactly `True` only when authorized. AskMill does not implement or interpret any application-specific access schema.
* `reserve(profile, request, request_sha256) -> str`, which must durably and exclusively reserve the exact run against the host's shared budget before any provider starts and refuse started, complete or uncertain replays across processes/restarts. A nonempty reservation is required.
* `finalize(reservation, settlement) -> bool`, which must durably record the observed outcome and return exactly `True`; refusal or failure prevents delivery. The host owns budget durability and origin authentication.

No gate is installed or approved by AskMill. Callback fixtures are software controls, not live access decisions. On post-run revocation, the attempt retains technical artifacts and a failed context recheck, but writes no result. The host must restrict those retained files and recheck authority before later publication.

## Execution and receipts

The engine checks its input and file pins, acquires the explicitly configured leases nonblocking, checks available memory, reserves the host budget, and starts only a new owned loopback service from the pinned binary/model store. Use a dedicated host-controlled model store and ensure the external service/runtime cannot download or reach a cloud model. The model tag/revision and embedding capability are checked before one `/api/embed` data request. A background monitor checks system availability and owned process-tree RSS; resource violations terminate only the owned process group. No provider switching, automatic retry or generated prose is used.

On a successful batch, a second empty-input `/api/embed` requests unload; `/api/ps` must confirm no model remains. The service and observed descendants are stopped, lease handles closed, the host ledger finalized and the context gate rechecked before `result.json` is created. The result has exact input IDs/hashes, finite normalized Float32 values and row hashes, actual token count and context allocation, and pinned references to the raw request, registered profile, runtime, provider response, settlement, ledger confirmation and context recheck. Technical completion is not legal, source-quality or semantic acceptance.

A timeout or uncertain in-flight data/cleanup request is never retried automatically. The engine stops only its owned service, records attempted versus acknowledged requests, An attempt writes its own `.unsettled` markers while holding the leases before service startup, and passes the lease handles to the owned provider. A crash leaves the markers in place. Only after acknowledged data and unload, confirmed owned-process cleanup and a settled monitor does it remove its own matching markers; it never clears a pre-existing or another attempt's marker. Uncertain attempts retain them for reconciliation. Failure artifacts are retained in the new attempt directory. The provider request timeout is bounded by the configured timeout remaining after setup; separately bounded process cleanup can extend beyond that value. A successful run makes one data and one empty cleanup endpoint request; metadata endpoints are separate.

This API is generic. Query/Backend own their private typed request/response translation, SOURCE_READ verification, B1-specific budgets, fresh profile/namespace registration and consumer acceptance. The old frozen Query host guard and source grants are not reused or widened. The same cached model and dimension do not by themselves prove that a new AskMill provider profile is compatible with an old frozen vector namespace: compare exact model/tokenizer/runtime behavior and qualify model-space parity before reuse.
