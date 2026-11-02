# Query embedding-batch offline contract inspector

This separately distributed tool inspects Query's `powerlex.query.embedding-batch.v1` request and `powerlex.query.embedding-batch-result.v1` response without running a model, provider, source-read check or resource guard. It requires the consumer-provided Query schema directory: the files must hash to `04f81352a5d277f60b35c2599c3bc49a373c8d8149b61907e94a59e7ec6d8109` (request) and `97098d9c6d521393672ac4644554d9843cc4e050279dabb8b3400eccd04e491c` (response). Query's unlicensed schemas are not redistributed here. The installed Python environment needs `jsonschema`.

```sh
/path/to/pinned/python /path/to/installed/tools/query_embedding_contract.py \
  --schema-directory /path/to/query/docs/contracts/embedding-batch-v1 \
  --request /private/request.json --request-sha256 EXACT_FILE_SHA256 \
  --askmill-profile /private/registered-profile.json --askmill-profile-sha256 EXACT_FILE_SHA256
```

Add `--response /private/response.json --response-sha256 EXACT_FILE_SHA256` for a retained response inspection. This tool treats the supplied profile file SHA as the request's `askmill_profile_sha256`; the registered profile's meaning and origin must be authenticated by the owning host and Query. Query confirmation of that hash domain remains pending. It validates the request schema, exact request/file refs and source hash consistency, canonical JSON provider and model-input profile digests, complete input hashes and unique IDs. It currently refuses batches over 32 instead of truncating or issuing multiple calls. For a response it verifies the published schema, request/scope/profile binding, exact row order/coverage, 768 dimensions, finite normalized Float32 little-endian row bytes and hashes, and all four receipt file hashes. Scope digest uses recursively key-sorted compact UTF-8 JSON; the existing Query `digestJson` is compatible with the schema's restricted scope values. The actual frozen provider and model-input canonical digests were checked against their separately pinned file-byte digests; they are distinct hash domains.

Results explicitly say source authority and receipt origins are not verified. A caller must independently authenticate current SOURCE_READ before and after long operations, profile/namespace and resource approval, receipt origin, provider/model execution, and legal/source/semantic gates. Synthetic test vectors only exercise software validation; they never qualify an encoder or a real source. This inspector does not convert its validation into a Query response or dispatch authorization.

## B1 integration blocker

The current released embedding bridge v0.1.1 delegates to Query's historical `cerc_embedding.py`: its resource guard is restricted either to the old first-source query or to an old canary requiring a combined document+query plan. It cannot be used for the new B1 source and separate document/query requests, and an old grant must not be reused or widened. A new B1-specific host resource/lease adapter and live before/after SOURCE_READ verifier, exact registered profile and scope hash contract, Query request/response integration, independent review, and consumer acceptance are required. The budget allows one document and one query data request plus their two owned-service cleanup requests only after those gates. No actual encoding has been performed by this inspector.
