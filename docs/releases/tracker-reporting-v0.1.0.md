# Tracker reporting v0.1.0 (tool-only)

Adds a bounded retained-evidence CLI for Map document-run intake 1.1. It emits
source-identified model/failed-invocation records with pinned receipts, separate
provider/Session timing, observed versus reserved token counters, null unknowns,
replay attribution and receipt-bound caller review. Native envelope/cache/schema
identity and exact frozen prompt JSON source subjects are checked before
emission. Missing source attribution produces a refusal instead of a guessed
ledger association.

This tool never imports the runner, creates Session, contacts a provider or
acquires model leases. AskMill inference remains at v0.1.0a6; no global launcher,
model/profile/default, frozen request or old result is upgraded. The adapter's
new consumer is an explicit installed tool path/file pin, independent of the
legacy a3 launcher and frozen Query bindings.

Qualified dependencies:

- AskMill v0.1.0a6 wheel SHA256
  `639a50e1096f7a8160e4b805e83e4ec48feb87d95c7675a5e6041a85260b758b`.
- Map v0.37.0 wheel SHA256
  `a26752bcb9ab845b2142fffd99ae4e9f9f8621cb7749368b2fab1bf42f1d24a6`.
- Packaged final requirements byte SHA256
  `1c4a29d0e12362c02cbd843318f53ea7db7620063f9961c4e81aa6d4ce75acd0`.

See [descriptor, CLI and registration boundaries](../TRACKER_REPORTING.md).
Install the verified archive into a new directory and use its exact script with
the separately qualified a6 Python. Validate/register its outbox with installed
Map 0.37 and explicit evidence roots. Neither a raw model receipt nor a metadata
summary alone is a document-run intake record.

Local qualification: 20 focused retained-evidence/control checks, source and
installed adapter runs, native installed-Map validation, idempotent append and
batch-registration/readback. Multi-PDF/replay/review control mutations are kept
outside the actual candidate outbox. Existing complete and zero-model-call
failure evidence retain their outcomes; no source, field, answer or legal
acceptance is promoted. No new inference, extraction, model download or CI run
was performed. Shared/golden registration is an independent Map-owner receipt,
not implied by a local check ledger or publishing this adapter. P3/P4 model tasks
remain gated on Central authority.
