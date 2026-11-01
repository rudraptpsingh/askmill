# AskMill phased implementation
Goal: one reusable local inference package for developers and application hosts.
No private product code or fixtures are needed to install or test.

| Phase | Goal | Gate / outcome | Status |
|---|---|---|---|
| 1 | Portable contracts and package | Clean install; strict request/profile/result schemas; no weights required | In progress |
| 2 | Warm sessions and receipts | Two items, one worker; replay acknowledged/lost results; preserve incomplete output | Planned |
| 3 | Providers and cleanup | MLX offline, external Ollama, timeouts; no external service termination | Planned |
| 4 | Codex and PDF2Data boundary | CLI/MCP share runner; old profile conversion; preserve consumer checks | Planned |
| 5 | Release qualification | Wheel clean install, CI, public fixtures, hardware smoke; downstream migration separately gated | Planned |

Each phase records the exact check and result here before proceeding.
Consumer migration must not replace existing inference until batch, evidence and exit-code parity pass.
