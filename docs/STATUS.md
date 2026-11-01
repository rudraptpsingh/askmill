# AskMill phased implementation
Goal: one reusable local inference package for developers and application hosts.
No private product code or fixtures are needed to install or test.

| Phase | Goal | Gate / outcome | Status |
|---|---|---|---|
| 1 | Portable contracts and package | Clean install; strict request/profile/result schemas; no weights required | Passed |
| 2 | Warm sessions and receipts | Two items, one worker; replay acknowledged/lost results; preserve incomplete output | Passed synthetic gate |
| 3 | Providers and cleanup | MLX offline, external Ollama, timeouts; no external service termination | Planned |
| 4 | Codex and PDF2Data boundary | CLI/MCP share runner; old profile conversion; preserve consumer checks | Planned |
| 5 | Release qualification | Wheel clean install, CI, public fixtures, hardware smoke; downstream migration separately gated | Planned |

Each phase records the exact check and result here before proceeding.
Consumer migration must not replace existing inference until batch, evidence and exit-code parity pass.

## Validation ledger, 1 November 2026
- Phase 1: editable install and seven strict contract tests passed; initial GitHub CI passed on Python 3.10, 3.12 and 3.13.
- Phase 2: five HTTP-stub session tests passed: worker reuse, restarted receipt replay, incomplete output, corruption rejection, device exclusion and timeout quarantine. First run caught a redirected close response and a cleanup race; both corrected before proceeding.
- Phase 3: Ollama digest preflight and optional offline MLX worker implemented. Model-directory identity hashes all local files. Real hardware qualification remains open; no owned Ollama service mode is claimed.
- Phase 4: non-mutating PDF2Data MLX profile conversion, JSON CLI and optional stdio MCP share the runner. Consumer default migration remains unqualified.
