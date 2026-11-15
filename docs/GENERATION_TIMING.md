# Inspect generation timing from retained receipts

`tools/inspect_generation_timing.py` reads an independently byte-pinned
structured Ollama v2 receipt and reports timing counters without starting a
runner, contacting a provider, loading a model, or exposing prompt or response
text. It checks the envelope checksum and key/result/runtime bindings. These
checks establish byte consistency, not provenance, authorization, settlement,
source quality or acceptance. Authenticate the expected receipt and its origin
separately. The tool refuses older receipts that do not retain a raw response.

```sh
python3 tools/inspect_generation_timing.py \
  --receipt /private/receipt.json --receipt-sha256 EXACT_SHA256
```

`attempt_seconds` is the original generation attempt measured by the runner:
it includes the provider call and post-call identity checks but excludes session
startup and shutdown. Provider durations are reported in nanoseconds and are
provider-reported measurements, not necessarily disjoint phases. Missing
fields remain null; never add or subtract them to invent unmeasured overhead.
The receipt alone cannot establish whether the model was already resident,
whether a later invocation replayed a cached result, or the duration of that
later invocation. Record those facts independently when needed.

A retained PowerLex calibration illustrates the gap. Two incomplete calls with
different prompts reported provider model-load durations of 2.800 seconds and
0.001 seconds and prompt-evaluation durations of 1.999 and 2.091 seconds. The
original runner attempt durations were 4.832 and 2.145 seconds. The data are
consistent with lower loading overhead on the second call, but the receipts do
not independently establish model residency before either call, total startup
cost, comparable workload performance, or quality. Both outputs were incomplete;
they are not report acceptance evidence. No latency threshold is implied.

For future measurements, retain a monotonic wall interval around session entry,
each dispatch and session close, bind each interval to its session and attempt,
and record replay and separately verified residency observations. Preserve the
raw provider counters and distinguish startup, loading, prompt evaluation and
generation. Do not use cached `Result.seconds` as a new invocation's latency.
