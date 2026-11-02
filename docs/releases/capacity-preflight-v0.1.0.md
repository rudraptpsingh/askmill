# Capacity preflight v0.1.0 (tool-only)

This first standalone tool release contains the no-container-read capacity
reporter, a separately authorized bounded GGUF metadata exporter, a maintained
CPU vocabulary-only tokenizer driver, an upstream Ollama renderer driver and
a pinned-plan static checker. The inference package remains v0.1.0a6; no global
launcher, provider service or consumer execution/default pin is changed.

The original report remains `askmill.capacity-preflight.v1` and keeps capacity
unknown when no tokenizer/rendering qualification exists. Separate stage
contracts are `askmill.gguf-metadata-export.v1`,
`askmill.offline-toolchain-plan.v1` and
`askmill.qwen35-static-qualification.v1`. Qualified upstream static fit and
actual runtime allocation/finish/settlement are distinct gates.

Use a separately installed a6 interpreter and the original qualified wheel:

```
639a50e1096f7a8160e4b805e83e4ec48feb87d95c7675a5e6041a85260b758b
```

See [no-container-read usage](../CAPACITY_PREFLIGHT.md) and the
[separate static qualification stages and build recipe](../OFFLINE_QWEN_QUALIFICATION.md).
Source archives include our helpers, documentation, boundary tests, existing
public software fixture, license and notices. Toolchains, third-party compiled
runtimes, model assets and private consumer inputs/receipts are excluded.

Validation includes 20 focused local software controls (one requires the
separately built CPU helper), native driver compilation, an actual zero-tensor
GGUF vocabulary parse, and a real candidate rendered/count-qualified with the
maintained upstream implementations. The original container was fully
stream-hashed only in the expressly authorized export stage; later counts
were sandboxed against network/original-container/lease access. Frozen
requests, previous reports and the global launch/profile configuration stayed
unchanged. These checks add zero source/document/model accuracy cases.

Consumer adoption is pending explicit acceptance of the exact helper/runtime/
profile/request/count pins. No inference was authorized or performed. An
accepted new plan still needs a separately authorized bounded execution and
caller-owned canonical/source/output/performance/settlement gates.
