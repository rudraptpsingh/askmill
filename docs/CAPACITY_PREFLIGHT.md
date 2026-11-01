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
