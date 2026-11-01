# PDF2Data integration

## Published PDF2Data: source-image field readings

The supported public baseline is PDF2Data 0.2.0rc7, commit
`9b1799e5a9474b9c2bd1ed43610b5446e15d6848`. CI installs that published revision,
creates a synthetic PDF, extracts its native fields, rerenders the source crop,
and reopens the imported reading through PDF2Data's validators.

From an AskMill checkout:
```sh
python -m pip install -e .
python -m pip install 'PDF2Data[pdf,proof] @ git+https://github.com/rudraptpsingh/PDF2Data.git@9b1799e5a9474b9c2bd1ed43610b5446e15d6848'
askmill --config profiles.json --store .local/receipts --lease /path/to/shared-gpu.lock \
  read-fields --profile qwen --request /path/to/witness-request \
  --output /path/to/new-reading --max-tokens 2048
```

Prepare the request with PDF2Data's existing `fields` and `field-witness prepare`
commands. AskMill uses the consumer's blind transcription prompt and image hashes,
keeps a warm session across regions, then calls its existing `import_reading` API.
The caller's native text is never supplied as a transcription answer.

The output is a normal PDF2Data reading bundle. It retains the raw readings,
image/source pins, runtime/model identity and links to AskMill execution receipts.
The import deliberately retains PDF2Data's
`operator_import_not_inference_verified` attestation. An execution receipt does
not upgrade that consumer attestation or clear review holds. Repeated executions
of the same profile produce the same reader fingerprint. A real-model smoke read
`Code: 42 END` from a generated PDF and reverified all source files unchanged.

Exit 3 preserves a token-limited reading as incomplete. Output and receipt stores
must be outside immutable input bundles. AskMill neither compares readers nor
grants consensus, source-quality approval or legal approval.

## Named AI / formula-gates branch

An optional `pdf2data-askmill` bridge routes the MLX Session boundary of a
separately installed PDF2Data checkout that provides `local_ai`:
```sh
pdf2data-askmill --store .local/receipts --lease /path/to/shared-gpu.lock -- \
  ai run qwen --config /path/to/pdf2data/models.json \
  --prompt 'Read exactly.' --image crop.png --output /path/to/new-run --json
```

Its local validation baseline is commit
`cb3c0c7088d0c24f059e8d76483d75b274893605`. That commit was **not available on
GitHub at validation time**. The public rc7 baseline does not contain those
named-AI/formula-review commands. The bridge reports unsupported_consumer for an
installation without them. Do not install an unrelated PyPI package to obtain
this feature.

Five local conformance tests compare the original and bridged paths:
add/list/probe, prompt/image ordering, token budgets, one model load per batch,
output hashes and receipts, exit 3 on truncation, and two-page formula-review
reopening. Device and peak-memory metadata are preserved. Wrong formula readings
remain unverified, and source flags/files remain unchanged. HTTP calls on this
legacy bridge retain the original consumer's behavior; only MLX is redirected.
No existing default or user configuration is rewritten.

## Integration boundaries

The Python/CLI integration does not require either project's MCP extra. AskMill's
optional MCP server is tested independently. PDF2Data currently declares a
different major MCP dependency; use separate processes/environments if enabling
both MCP servers. The published native integration tests do not install PDF2Data's
MCP extra.

Future consumer-default migration still needs the owner's source-bound bilingual
and held-out cases. A generated PDF proves the integration mechanics, not
accuracy on regulatory PDFs.


For a specialist profile such as PaddleOCR, a3 permits an explicit task prompt:
add --prompt 'OCR:' to read-fields. The actual prompt is retained in
external-readings.json alongside execution receipt IDs. The default remains
PDF2Data's transcription prompt when no override is supplied.
