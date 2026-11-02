# Explicit embedding bridge v0.1.1 candidate

This separately distributed CLI/SDK exposes a **registered** local embedding batch; it does not add embedding to the existing `askmill list` command or modify global profiles. It invokes the exact host-selected, byte-pinned Query `cerc_embedding.py` adapter, which delegates to the existing EmbeddingGemma host and its resource guard. There is no model discovery, direct Ollama fallback, automatic retry, substitute encoder, generation or default profile. This bridge is not an independent embedding runtime and is not qualified for real sources until the consumer installs and accepts the exact artifact and implements/authenticates the source gate.

The supported frozen vector space is `embeddinggemma-2:270m`, model manifest `20c5a2af114e1813484d1611b27a57c33398aee4f59c39359c5a28af9d1547e7`, Ollama MLX NVFP4, 768 float32 dimensions, mean pooling, normalized, 8192-token context, tokenizer SHA `4d777ef5bdc1aa36227abdfb77c3e49e7b9c892d16e1b6bda41c393504828be4`. The existing host enforces its exact profile, tokenizer, fully supplied input, token count, no truncation, shared device leases and owned-service cleanup. Prefixes and input segmentation are caller-owned and must match the profile's document/query configuration; the bridge never inserts or clips text. Matching dimensions alone does not establish model-space compatibility.

## Registry and current authorization

A private registry is pinned by exact file SHA256 and contains `schema_version: askmill.embedding-registry.v1` and `profiles: {<name>: <entry>}`. Each entry has exactly:

* `adapter`: absolute path/SHA256 of Query's `scripts/lib/cerc_embedding.py`.
* `configuration`: absolute path/SHA256 of a **new current** Query encoder configuration, including its existing pinned provider/model-input profiles, `host_scripts`, host file pins and exactly one current `resource_policy` or `live_query_policy`. Existing Query code validates that policy and planned exact inputs. Never reuse a source-scoped grant for a different source, workspace or job.
* `source_gate`: absolute path/SHA256 of an independently trusted host Python file exposing `verify_source_read(request, configuration)`. It must authenticate the current principal, job, workspace, source grant and the exact request's source/input relationship. The bridge refuses unless it returns exactly `True`. A SHA-verified file, fabricated callback or old grant is not itself proof of authorization; the host must independently provision and authenticate this gate.
* `dependencies`: array of absolute path/SHA256 refs including Query `scripts/lib/cerc_resources.py` and the host `run_regulatory_local_embeddings.py`, `prepare_regulatory_local_embedding_inputs.py`, and `plan_regulatory_best_effort_embeddings.py`. Host imports and runtime packages must also be pinned and accepted by the consumer.

The registry, source-gate code and dependencies are executable trust roots, not sandboxes. Protect and independently authenticate them. A synthetic test callback demonstrates orchestration only and must never stand in for the live Backend SOURCE_READ gate.

## Command and contract

```sh
/path/to/qualified/python /path/to/embedding_bridge.py list \
  --registry /private/registry.json --registry-sha256 EXACT_SHA256
/path/to/qualified/python /path/to/embedding_bridge.py embed \
  --registry /private/registry.json --registry-sha256 EXACT_SHA256 \
  --profile explicit-name --request /private/request.json \
  --request-sha256 EXACT_SHA256 --output /private/new-attempt-dir
```

`askmill.embedding-request.v1` contains exactly `schema_version`, `mode` (`documents` or `queries`), `source_read_ref` (`{path, sha256}` to the current independently verified grant), and `inputs`: 1–32 ordered `{id, text, sha256}` rows. The row hash is SHA256 of exact UTF-8 text; IDs are unique. The request and grant remain private. The existing Query resource policy must bind the same mode and complete exact ordered inputs; its implementation verifies the actual tokenizer count and refuses truncation. Each attempt invokes its host encoder at most once for one batch; failure preserves the reservation directory and is never retried automatically.

The output contains Query's native batch receipt and `.npy` vector artifact, owned-service `cleanup.json`, and a separate `askmill.embedding-receipt.v1` with the exact profile/configuration/adapter/source-gate pins, ordered IDs and input/float32 row hashes, dimension, one data model call and native artifact SHA. It checks every row is finite and normalized, matches the saved float32 artifact and native receipt, and that observed token counts match the provider. Successful output requires the host to report owned-service stop and model unload. The host owns shared-lease handling and resource receipt; this bridge does not independently attest a host's policy, cleanup or file origins. The underlying host also sends an empty-input `/api/embed` cleanup request. A successful receipt requires exactly two successful `/api/embed` entries in the newly owned service log, records one native data call and one cleanup request separately, and pins that log. This accounting relies on the authenticated Query host implementation and its exclusive owned service; the host must verify the log's origin. The empty request is a cleanup control, not text inference.

## Validation and remaining gates

Ten synthetic offline unit controls exercise one batch, exact hashes/rows, bad token counts, nonfinite vectors, missing resource policy, wrong source gate, changed dependency, duplicate inputs and replay refusal. No actual source, weights, provider, or model is used. Backend/Query must supply and qualify their current B1 SOURCE_READ verifier, resource policy and registered new B1 profile, frozen input refs and call budget, independently accept the bridge release, and keep the approved smoke budget of one data request plus one cleanup request. The separate authorized two-call smoke test cannot start before those gates. Bulk indexing needs its own policy. No source quality, legal, semantic retrieval or client approval follows from embeddings.
