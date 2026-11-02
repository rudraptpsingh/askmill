# Capacity preflight v0.1.0 (tool-only)

This is the first standalone release of the repository capacity evidence
helper. It is separate from the AskMill inference package, which remains at
v0.1.0a6. No global launcher, provider, model, context or consumer execution pin
is changed by this release.

The helper records strict request/schema admission and offline profile/manifest
metadata, keeps unqualified tokenization/context fit unknown, and now identifies
missing dependencies explicitly. It does not contain an offline tokenizer or
an implemented capacity-pass path. The evidence contract remains
`askmill.capacity-preflight.v1`, with additive missing-dependency fields.

Run the extracted `tools/capacity_preflight.py` with a separately installed,
qualified AskMill v0.1.0a6 interpreter and the original wheel. The qualified a6
wheel SHA-256 is:

```
639a50e1096f7a8160e4b805e83e4ec48feb87d95c7675a5e6041a85260b758b
```

See [usage and dependency qualification plan](../CAPACITY_PREFLIGHT.md).
The archive contains the helper, guidance, affected software controls, existing
public fixture, license and notices. Private consumer inputs, reports and model
assets are excluded. Verify the release archive against its checksums and pin
the helper file hash independently.

Validation: ten focused offline software controls, lint/format, and two separate
retained real-request admission checks against the immutable a6 validator.
Audit guards observe no network, runner import, lease access, weight read or
model inference during those request checks; frozen inputs and old evidence
stay unchanged. The invalid provider-pattern descriptor is still refused; the
compatible descriptor passes schema with capacity unknown. These checks add
zero model/source/document accuracy cases. Public CI is separately linked on
the owning commit.

Consumer acceptance remains pending. A caller must explicitly accept this
helper artifact and its additive report fields. That acceptance would not
approve tokenizer equivalence, context fit, inference dispatch, canonical
postvalidation, source semantics or a different execution runtime.
