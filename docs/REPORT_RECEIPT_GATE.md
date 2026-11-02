# Report receipt gate v0.1.0

This standalone offline CLI verifies one retained text-only Ollama structured-response receipt using the separately installed AskMill a6 runtime. It does not dispatch, retry, start a provider, inspect leases, or authorize a report. It checks native request/profile/runtime and receipt/settlement cross-bindings with `verify_cached_record`, then requires exact stdout/result equality, completed non-replayed schema-valid output, assistant raw text equality, no tool calls, explicit `done_reason=stop`, consistent nonnegative output counts, and the host's exact closed-lease count. The gate must be run separately for generation and review.

## Input and use

Create a new private manifest with exactly these fields. Each named file reference is `{ "path": "/absolute/path", "sha256": "<sha256 of exact file bytes>" }`; each JSON file must reject duplicate keys. `request` and `profile` contain the independently expected full AskMill Request v2 and profile objects, `runtime` the expected native runtime object, `receipt` and `settlement` the retained native envelopes, and `stdout_result` the separately retained parsed result. The manifest itself must be pinned in an independently trusted host job record; inputs copied from a receipt alone cannot establish origin or authorization.

```json
{
  "schema_version": "askmill.report-receipt-gate.v1",
  "request": {"path": "/private/request.json", "sha256": "..."},
  "profile": {"path": "/private/profile.json", "sha256": "..."},
  "runtime": {"path": "/private/runtime.json", "sha256": "..."},
  "receipt": {"path": "/private/receipt.json", "sha256": "..."},
  "settlement": {"path": "/private/settlement.json", "sha256": "..."},
  "stdout_result": {"path": "/private/stdout-result.json", "sha256": "..."},
  "lease_handles_closed": 2
}
```

```sh
/path/to/pinned-a6/python /path/to/report-receipt-gate/tools/report_receipt_gate.py \
  --manifest /private/gate-manifest.json --manifest-sha256 EXACT_SHA256 \
  --output /private/new-gate-result.json
```

The output path must not exist. On refusal, the program exits nonzero and writes no successful result. Keep raw output and failure evidence private. Hashes provide byte integrity, not signatures or independent origin authentication. The host must independently pin the installed runtime/wheel and gate artifact, check current job authority and call reservations, authenticate file origins, and reconnect each phase to its exact run, pack, input, schema and source references. This tool does not verify which program created a receipt. Its result explicitly leaves `source_completeness` and `context_fit` as `not_checked` and does not authorize dispatch or domain acceptance.

## R1 integration plan

1. Backend binds a fresh job, source grant, complete source/context inventory, generation/review input and schema projection, pinned AskMill profile and runtime, and two phase budgets. Unknown or withheld context remains visible; host checks it against caller requirements.
2. Before each authorized dispatch, run the appropriate offline fit qualification for that exact request, renderer, tokenizer, model and output reserve, and independently check runtime allocation. If unavailable or unmatched, refuse: byte counts and doctor checks do not establish fit. The existing [Qwen static tool](OFFLINE_QWEN_QUALIFICATION.md) covers only its qualified scope and expressly does not prove active-provider identity or allocation.
3. The host's durable runner makes at most one explicitly authorized call per phase, with no fallback or automatic retry; it retains request, raw stdout and native receipt/settlement. An uncertain call remains uncertain. Stop before review on a refused generation.
4. The host pins independent expectations and runs this gate on each retained phase. Validate the unmodified Query schemas and reconstruct source, paragraph and claim bindings separately; a passed receipt gate is not source support, model quality, legal approval or delivery permission.
5. Backend performs isolated installed consumer controls and explicitly accepts the exact gate artifact. A real provider qualification requires a later separate authorization, actual phase-specific receipts and settlement, and all current authority and fit gates.

The 73 KB review probe is a byte measurement, not a token count or proof of fit. The Query report input and prepared source inventory belong to Query/Backend; AskMill source records are provenance metadata and do not by themselves transmit or prove complete context.
