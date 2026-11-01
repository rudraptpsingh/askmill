# AskMill phased implementation

Goal: one reusable local inference package for developers and application hosts. No private product code or fixtures are needed to install or test.

| Phase | Goal | Gate / outcome | Status |
|---|---|---|---|
| 1 | Portable contracts and package | Clean install; strict request/profile/result schemas; no weights required | Passed |
| 2 | Warm sessions and receipts | Two items, one model load; replay committed items; preserve incomplete output | Passed synthetic gate |
| 3 | Providers and cleanup | MLX offline, external Ollama, timeouts; no external service termination | Real synthetic MLX and Ollama smoke passed; ownership limits below |
| 4 | Codex and PDF2Data boundary | CLI/MCP share runner; old profile conversion; preserve consumer checks | CLI/MCP and conversion passed; downstream adoption open |
| 5 | Release qualification | Wheel clean install, CI, public fixtures, hardware smoke | Wheel built; clean-wheel test suite passed; remote CI passed on Python 3.10/3.12/3.13 |

## Validation ledger, 1 November 2026

- Phase 1: editable install and seven strict contract tests passed. Initial GitHub CI passed on Python 3.10, 3.12 and 3.13.
- Phase 2: HTTP-stub session tests check worker reuse, restarted receipt replay, incomplete output, corruption rejection, device exclusion and timeout quarantine. Synthetic MLX modules prove one load across two requests and replay after restart without another load. An owned-worker timeout is reaped and a retry succeeds. A parent SIGKILL during the second item preserves the first committed receipt and keeps the GPU lease with the surviving worker until it exits.
- First session run exposed a redirected shutdown response and a cleanup race. Both were corrected before phase 3. A later formatting pass removed a fixture import; moving the shared fixture to conftest.py resolved it before the final suite.
- Phase 3: actual cached Qwen3-VL-8B through MLX read the synthetic 42 twice in one worker. Replay reused its receipt. Both existing host GPU leases were acquired. Actual Qwen3 8B through a dedicated local Ollama test server answered 6 + 7 as 13. The test host verified unload and stopped only its own server.
- Model-directory identity hashes all local files; Ollama preflight verifies its tag and digest. Timing summaries in [validation evidence](validation-2026-11-01.json) exclude hashing/setup. These smoke tests establish neither provider superiority nor real-document accuracy.
- Phase 4: CLI preserves incomplete output with exit 3. An actual MCP stdio client initializes, discovers and invokes the same runner. PDF2Data MLX profile conversion preserves interpreter/cache paths and never edits the source file. Skill validation passed. The CLI supports bounded batch JSON and MCP exposes run_batch, both keeping one warm session. Installed host configuration can supply shared lease_paths; a busy configured lease prevents generation. The shared MLX shim and original PDF2Data Session both read the same real synthetic crop as 42; the second shared call replayed its receipt. This checks only the Session boundary.
- 24 automated tests pass from the source install. A separate virtual environment installs the built wheel and runs the same tests without an editable package. Public examples use synthetic text and a generated number image.

Final source revision `57c558b` passed [GitHub CI](https://github.com/rudraptpsingh/askmill/actions/runs/41285809014) on Python 3.10, 3.12 and 3.13. The same revision passed 24 tests from the source install and from the rebuilt wheel. AskMill's executable and skill are installed on the development host; its qwen profile preserves the existing PDF2Data config and uses the host's existing GPU locks. Fresh-chat usage and downstream product acceptance remain separate gates.

## Remaining gates and next work

1. The opt-in MLXSession compatibility adapter passes a real synthetic side-by-side reading against the original PDF2Data Session. Next prove two-crop order, prompt, budget, one-load behavior, review holds, receipts and exit-code parity against the current consumer. Do not switch defaults yet.
2. Ollama identity is checked before and after generation; a mid-call tag change is rejected without committing a result. Next pin runtime versions in cache identity and define settlement receipts. Owned Ollama mode, crash recovery and memory admission are still unimplemented.
3. Owned MLX parent-crash recovery passes a synthetic test: kill the parent during item two, retain the inherited worker lock, replay item one and retry item two. Full host-death and external-server crash recovery remain open. Queue fairness, multi-user scope enforcement and authorization belong to a separately qualified host layer.
4. Run a real bilingual/source-bound case downstream and the Query/Impact source validators. A synthetic 42 and arithmetic question do not qualify that product path.
5. Use the installed skill in fresh chats in two repositories and verify a real code finding. Keep cloud profiles explicitly selected and out of local-only fallback.

The default runner supports external Ollama and owned MLX workers on POSIX. It intentionally rejects OpenAI-compatible profiles until model attestation exists. No consumer default or product review status has changed.

## Cross-chat continuation

Read this file and AGENTS.md. Inspect the current revision and rerun the affected checks. Take the first remaining gate, record the exact command and outcome, and commit the validated increment. Keep private model configuration, raw receipts and domain fixtures outside this repository. The goal remains active until required downstream gates are met.
