# Initial runner completion audit

This audits the active objective, including its requirement to record remaining
hardware/product gates. It qualifies the listed alpha interfaces; future
consumer default replacements and the application itself are not claimed built.

| Requirement | Authoritative implementation and evidence |
|---|---|
| Open-source independent repo | Public rudraptpsingh/askmill; MIT LICENSE and THIRD_PARTY_NOTICES; standalone wheel/base install, no Powerlex/customer fixtures |
| Portable profiles and contracts | contract.py, profiles.py, schemas; strict invalid-input tests; non-mutating old-profile conversion; model and runtime identity checks |
| Local text and vision | Persistent worker with existing MLX interpreter, offline local weight load; Ollama local API; actual Qwen text and source-crop smoke evidence |
| Bounded sessions | Batch count/deadline constraints; image/output limits; one model load per batch; device exclusion; actual CLI interrupt/timeout and owned/external parent-crash tests |
| Immutable execution receipts | Exact frozen bytes, prompt, settings, model/runtime identity; atomic commit/fsync, integrity verification, replay and corruption tests; distinct immutable settlement evidence |
| CLI and optional MCP/skill | run/batch/doctor/list/import-pdf2data/read-fields; error/cancel/incomplete exits; actual stdio MCP client; validated installed skill; no new-chat speed claim |
| PDF2Data compatibility | Public rc7 field-witness adapter with genuine extraction/rerender/import tests and real model reading; local legacy CLI/formula-review parity with explicit unpublished baseline |
| Phased plan and validation | STATUS.md, source/wheel suites, CI matrix and public consumer CI, recorded exact public revision |
| Remaining gates recorded | STATUS.md lists consumer-default, runtime/host, bilingual/corpus, fresh-chat and end-to-end benchmark gates without claiming them passed |

The raw test/hardware receipts stay local; public validation summaries contain
synthetic cases, exact model identity and test scope. A green schema or completed
generation does not establish source correctness. Source flags, native files
and review holds remain owned by the consumer.
