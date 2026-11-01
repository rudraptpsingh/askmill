# AskMill

Run local text and vision models from your code, terminal, or coding assistant.

**Early alpha for macOS/Linux (Python 3.10+).** A small shared runner with a Python API, JSON CLI and optional stdio MCP server. Use Ollama for local text/images or an existing MLX-VLM environment for Apple Silicon vision. Model weights are installed separately.

## Install and run

From a checkout:
```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev,mcp]'
python -m pytest
```

1. Start your locally installed Ollama service and install a model using Ollama's own instructions.
2. Copy [profile.template.json](examples/profile.template.json) to a local configuration file. Set the exact installed model name and digest from your service's `GET /api/tags`. A tag alone is not a pinned identity.
3. Run a bounded task:

```sh
askmill --config profiles.json doctor --profile dev-text
askmill --config profiles.json --store .local/receipts run \
  --profile dev-text --input examples/failing-test.txt --max-tokens 512
```

The CLI always prints JSON. Exit 0 means completed; 3 preserves incomplete output; 2 means failure; 130 means interruption. A completed response still needs your task's tests or evidence checks.

**Use the same device lease paths across every caller.** Set `"lease_paths": ["/absolute/shared-gpu.lock"]` at the top level of the local profile file, or repeat global `--lease PATH` for multiple existing locks. AskMill's default lock does not coordinate unrelated runtimes that use different paths. Keep receipt stores private to each authorized workspace; they contain exact prompts and image bytes.

## Vision and Python batches

The optional MLX runtime must have MLX-VLM and cached weights. AskMill can use a separate existing interpreter; its worker requires only the runtime's dependencies, not a second AskMill installation. Worker environments explicitly disable Hugging Face downloads.

To convert an existing PDF2Data MLX profile without changing its configuration:
```sh
askmill --config /path/to/pdf2data/models.json import-pdf2data --profile qwen > profiles.json
```

Conversion hashes the cached model files to pin their contents. It can take time for large weights. For a new profile use `askmill.profiles.model_revision(model_path)` and the [profile schema](schemas/profile.json).

```python
from askmill import Request
from askmill.profiles import load
from askmill.runner import Session

profile = load("profiles.json", "qwen")
with Session(profile, store=".local/receipts", lease="/path/to/shared-gpu.lock") as session:
    for crop in ("first.png", "second.png"):
        result = session.run(Request(prompt="Read exactly.", images=[crop]))
        print(result.text, result.complete)
```

For CLI batches use `askmill batch --profile NAME --request batch.json` with `{"schema_version":"askmill.batch.v1","requests":[{"prompt":"first"},{"prompt":"second"}]}`. MCP exposes the same warm path as `run_batch`. Batches contain at most 16 items and one hour of total generation deadlines.

The worker loads the model once per session. Every item freezes actual inputs and commits an integrity-checked receipt atomically. Cache identity includes the worker/runtime versions and transport implementation hash. After closure, a separate integrity-checked settlement receipt records worker reaping, closed lease handles and whether the external request acknowledged termination. It never claims to stop an externally owned server. A result produced before a parent crash may have no settlement receipt; do not infer cleanup from result existence alone. Replaying the same request/profile in the same store reuses a completed item, including an incomplete result; change the request/budget for a fresh attempt. A model process interrupted before commit is retried by the caller. The [synthetic vision example](examples/vision_batch.py) reads a printed 42 twice.

## Coding assistants

The optional MCP command is `askmill --config /absolute/profiles.json --store /workspace/receipts mcp`. Configure your MCP client to launch that executable with those arguments. The `run` and `run_batch` tools use the same session and receipt implementation as Python and the CLI.

The reusable skill is [skills/askmill/SKILL.md](skills/askmill/SKILL.md). Copy its folder to your coding assistant's skill directory after installing the executable. It guides bounded local calls and verification; it does not replace the parent assistant.

## PDF2Data

Use `askmill read-fields` with PDF2Data's published field-witness request/import
API. The integration preserves native fields, source hashes and review flags.
See [the exact supported revision and commands](docs/pdf2data.md). The legacy
named-AI bridge is separately qualified against a local, unpublished feature
branch; it is not a public rc7 capability.

## Ownership and limits

External Ollama is never stopped or unloaded by AskMill. If a request times out, the client cannot prove the server stopped generating. AskMill writes `LEASE.unsettled` markers and rejects further runs using those leases. Verify the external workload settled before manually removing the markers. An owned MLX worker is stopped and reaped before its lease is released. Worker-inherited lock descriptors keep the lease held while that worker lives.

Supported in this alpha: strict contracts, text/vision, local profiles, receipt replay, bounded sessions, generation timeout, device exclusion, CLI, MCP and non-mutating PDF2Data MLX profile conversion. Local loopback/private HTTP endpoints only, with proxies and redirects disabled. No automatic cloud fallback or model downloads.

Not yet qualified: owned Ollama server management; OpenAI-compatible model attestation; Windows; shared multi-user service/authentication; queue fairness; full host-death/external-server crash recovery; memory admission; provider performance comparisons; PDF2Data/Query default migration. OpenAI-compatible profiles are explicitly rejected by the public runner until identity verification is implemented.

The opt-in `askmill.pdf2data.MLXSession` shim preserves the legacy generate/close boundary for MLX; full consumer migration is separately gated.

Evidence review, PDF cropping, source corrections, domain acceptance, batch retries and access checks remain with the caller. Receipts are integrity checks, not signed provenance. Protect their store against unauthorized writes. These checks do not establish legal accuracy or production readiness.

See [phase gates and validation evidence](docs/STATUS.md), [contributing](CONTRIBUTING.md), and [third-party notices](THIRD_PARTY_NOTICES.md).
