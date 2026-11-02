# Offline capacity preflight

`tools/capacity_preflight.py` is a checkout utility for read-only request,
profile and model-metadata evidence. It uses a separately installed, pinned
AskMill wheel for strict contract validation. It does not initialize Session,
import a transport, acquire a model lease, contact a provider, read weights,
run a tokenizer, download a model or change any execution profile.

This is **not** an `askmill preflight` CLI command or an MCP inference tool.
The utility is maintained in the repository, separately from the released
inference runtime. Pin its commit/file hash and the validator wheel independently.
The utility records its own SHA-256. No consumer runtime is repinned by using it.

## Usage

Run from the checkout with the Python executable of an immutable installed
release, rather than the checkout's editable development environment:

```sh
/path/to/pinned-release/bin/python tools/capacity_preflight.py \
  --wheel /path/to/qualified/askmill.whl \
  --wheel-sha256 EXACT_WHEEL_SHA256 \
  --config /path/to/private/profiles.json \
  --profile SELECTED_PROFILE \
  --request /path/to/frozen/request.json \
  --model-manifest /path/to/original/content-addressed/manifest \
  --blob-directory /path/to/ollama/models/blobs \
  --execution-runtime /path/to/frozen/execution-runtime.json \
  --output /path/to/private/new-preflight.json
```

The wheel checksum and installed Python payload are verified before validation.
Use a trusted wheel; checksum comparison is integrity verification, not a signature.
The output path must not exist. Keep request files and reports in private storage.
Freeze/check the request hash independently before and after inspection.
`--execution-runtime` records an optional opaque JSON reference and its declared
version; it does not start, inspect the installed payload of, or qualify that runtime.
The preflight validator version may differ from the consumer execution version.
A schema pass under the validator does not certify a different execution version.

Model metadata arguments are optional. When supplied, they support an original
Ollama manifest whose raw SHA-256 matches the selected profile revision, with at
most 32 layers. A local tag manifest may have been rewritten by Ollama; use the
original content-addressed manifest rather than treating a different tag-file
hash as proof of revision drift. Only bounded configuration, template, system
and parameter blobs are opened and hashed. Declared model/projector digests
and sizes are recorded without opening those containers. A metadata alias to
a declared non-metadata container is refused before reading it. This path does
not qualify arbitrary manifests, MLX tokenization or a live Ollama tag.

## Report and gates

The output contract identifier is `askmill.capacity-preflight.v1`:

| Evidence | Meaning |
|---|---|
| `preflight_install` | Validator version, wheel bytes/hash and installed Python payload comparison |
| `execution_runtime_ref` | Optional frozen execution reference; not started or requalified |
| `profile` | Selected name, provider, model revision, generation settings, serialized-profile hash and exact registry pin |
| `request` | Raw file pin, prompt UTF-8 bytes/codepoints/hash, counts, response-schema pin, strict input/schema gate and bounded errors |
| `model_metadata` | Manifest/config/template pins, declared renderer/parser, inherited model defaults and unopened tensor identities |
| `provider_input_roles` | Prompt, source provenance, native schema/grammar, unknown framing overhead and thinking setting |
| `tokenization` | Exact input count and justified conservative bound, both currently null/unknown |
| `capacity` | Declared context, reserved output, arithmetic input budget and unknown allocation/fit |
| `boundaries` | No inference/Session/leases/weight reads; no execution or domain approval |
| `measurement` | Preflight-only elapsed time; no established performance threshold |

Prompt byte or codepoint counts are **not token counts or safe token bounds**.
No qualified offline tokenizer and complete provider renderer are implemented
here. A template-layer hash and an embedded tokenizer container digest do not
establish complete rendering/tokenization identity. Native context limits and
actual live allocation remain unknown. This utility therefore cannot report fit.

For example, declared context 8192 with output reserve 2048 leaves an arithmetic
input budget of 6144 *if the provider honors that setting*. It says nothing about
whether the rendered request fits. Generation settings are intended profile
settings, alongside recorded model defaults; they are not live attestation.

AskMill passes the prompt as user-message content. Source records are provenance
metadata, not additional message content. Request-v2 response schemas are passed
as Ollama's native `format` grammar; if a caller also embeds schema text in the
prompt, that text contributes to input. System/template/grammar processing,
images and thinking can require additional qualification. This tool neither
removes duplicate instructions nor strips unsupported schema keywords.

| Exit | Meaning |
|---|---|
| 2 | Strict Request/schema rejected; diagnostic report retained |
| 3 | Strict Request/schema passed; tokenization and capacity remain unknown |

Other failures, such as duplicate-key JSON, bad metadata, wheel mismatch or an
existing output path, raise an error and may have no report. Archive stderr and
the frozen input pins as caller-owned failure evidence. There is currently no
successful capacity/fit exit. Unknown capacity does not authorize dispatch.

Keep input, model identity, capacity, authorization/scope, output, source/domain
acceptance and performance gates separate. Timing excludes interpreter/import,
wheel verification and report-write costs. It is not inference latency or p95.
Source-only routes should not initialize an AI runner to use this utility.

## Validation

`python -m pytest -q tests/test_capacity_preflight.py` exercises offline software
controls using the existing public fixture: unknown capacity, unchanged inputs,
invalid envelopes, metadata size refusal before open, weight-container alias
refusal, manifest pin mismatch and wheel checksum mismatch. These add no model
or source accuracy cases. Actual consumer requests and guard evidence stay
private, including prior failed descriptors; a new descriptor never replaces
its frozen predecessor.

## Qwen3.5 dependency investigation

A declared renderer is not the same as the stored template text. In Ollama
v0.40.13, the Qwen3.5 selection uses its built-in renderer, including role
framing and an empty thinking block when thinking is disabled. Merely counting
the prompt or rendering the 13-byte passthrough template would miss that path.
See the pinned [renderer selection](https://github.com/ollama/ollama/blob/04088e7c9d41cba5d33bafbf788d87a465c79d5b/model/renderers/renderer.go)
and [Qwen3.5 renderer](https://github.com/ollama/ollama/blob/04088e7c9d41cba5d33bafbf788d87a465c79d5b/model/renderers/qwen35.go).
These sources are a candidate implementation for qualification, not attestation
that a local binary or active service matches the tag.

A provider's render-only switch is not automatically a no-model preflight.
The same version's chat handler schedules a runner before its debug-render
return. The provider may also prepend model-defined messages/system text and
clamp context to runner capacity. Calling that route would violate the offline
boundary; no such call is used here. See the pinned
[chat handler and message preparation](https://github.com/ollama/ollama/blob/04088e7c9d41cba5d33bafbf788d87a465c79d5b/server/routes.go)
and [render/tokenize path](https://github.com/ollama/ollama/blob/04088e7c9d41cba5d33bafbf788d87a465c79d5b/server/prompt.go).

The publisher provides separate [Qwen3.5 tokenizer assets](https://huggingface.co/Qwen/Qwen3.5-9B/tree/21eca8a083a2121a92fba681f4a7c72cf20ff1a7),
but their existence does not prove correspondence with a selected Ollama
container's vocabulary, merge ranks, special-token IDs, pretokenization or
BOS/EOS behavior. A cached Qwen3-VL tokenizer is a different model's asset.
Do not substitute either one on the strength of a family name. A bytes-based
upper bound would also need proof of tokenizer normalization/expansion and
complete framing; no such proof is currently available. An upper bound above
the available input budget would not prove overflow, either.

The utility reports machine-readable `tokenization.missing_dependencies` and
`capacity.missing_dependencies`; it does not accept unqualified count overrides.
The precise missing pieces are revision-bound tokenizer metadata and its
implementation, complete provider-renderer/build identity and evidence for
native context/allocation. Installing a generic tokenizer library alone does
not satisfy them.

A safe **new plan**, separate from a frozen request/runtime, has these phases:

| Phase | Goal | Required outcome |
|---|---|---|
| 1. Obtain metadata only | Acquire a trusted tokenizer sidecar tied to the exact model container digest, plus context/config metadata | Versioned asset hashes and vocabulary/merge/special-token/BOS/EOS equivalence evidence; no family-name substitution |
| 2. Qualify rendering | Bind the provider binary/build and renderer source; establish model system/default messages and exact thinking/framing behavior | Complete rendered request bytes with implementation and input pins, without starting a runner |
| 3. Count offline | Use a separately pinned CPU tokenizer implementation with network disabled and an allowlist of metadata files | Exact token count or a proved conservative bound, with weight/lease/provider access refused |
| 4. Gate capacity | Combine the count/bound, native limit, output reservation and allocated-context evidence | Explicit fit/overflow/unknown; no clipping, default change or dispatch authority |
| 5. Publish and adopt | Release the qualified helper and have each consumer accept its exact version | Immutable artifacts and caller-owned acceptance; existing execution/profile pins unchanged until separately adopted |

If the only tokenizer copy is embedded in a weight container, obtaining an
export requires a separately scoped packaging/extraction plan. This preflight
does not open that container, even to inspect its header. A trusted existing
export with equivalence evidence is preferable within this boundary. A later
runtime parity check involving a provider/runner would also require its own
plan and authorization; it is not an offline tokenizer test.

The retained schema failure teaches a different lesson: canonical caller
validation may include `pattern` constraints that the provider grammar subset
cannot accept. Keep the canonical schema and its postvalidation separate from
an explicitly prepared compatible provider schema. The utility must refuse
unsupported grammar, retain the frozen input, and leave that repair to the
caller. Removing duplicated inline schema text can reduce bytes but does not
qualify token capacity or relax caller semantics.

The dependency diagnostics are an additive report-v1 extension distributed in
a tool-only release. They do not introduce token counting or change the a6
inference package. Consumers must accept the new helper/artifact pin explicitly;
a new report does not replace an older frozen report or execution descriptor.
