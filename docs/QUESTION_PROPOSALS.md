# Source-ID-bound question proposals

This optional workflow supports the existing real-document QUERY → GAP → FIX →
REGRESSION suite. Proposal generation is separate from answer evaluation.
Use actual original/native records and Map type/section/required-field guidance.
The model proposes questions; it never supplies gold answers or expected facts.
No new engine or domain interpreter is required in AskMill.

## Contract and cheap admission

Prepare an explicit `askmill.request.v2` with a SHA-pinned response-schema
envelope. The consumer's output contract is `askmill.question-proposals.v1`:

| Field | Meaning |
|---|---|
| `schema_version` | Constant proposal contract version |
| `scope_sha256` | Constant hash of the exact native source scope |
| `proposals[].proposal_id` | Unique identifier for this proposed question |
| `proposals[].question` | Bounded question text; no answer, fact assertion or citation |
| `proposals[].intent` | One supplied Map requirement/intent label |
| `proposals[].supplied_source_ids` | Nonempty subset of the exact supplied source IDs |
| `proposals[].required_evidence_type_hints` | Supplied evidence-type labels, not evidence claims |
| `unresolved_items[]` | Supplied IDs, known missing dependency IDs, intent and bounded reason |

Generate a **closed** schema: `additionalProperties:false` at every object,
source/intent/dependency enums from the actual input, bounded strings/arrays,
and the scope hash as a `const`. An all-unresolved response with zero proposals
is valid when the source does not support useful questions. Do not invent an
example model output and count it as a run.

Before inference, the consumer verifies released schemas/package/model pins,
original/native hashes, authorized scope, source IDs, version/reading/rule
identity, Map context and budgets. Missing required table headers/cells, EM
inputs or governing documents block dependent interpretation. Retain
unreviewed source/customer states and unresolved dependencies explicitly.
AskMill freezes `sources` metadata; reopening it and checking permissions remain
consumer work. A known absent source is never filled by prompt guessing.

## One bounded session

Only admitted requests reach the runner. These SDK calls use the same leased
path as CLI `run --request` and `batch --request`:

```python
from askmill import Batch, Request
from askmill.jsonio import load as load_json
from askmill.profiles import load
from askmill.runner import Session

registry = load_json(config_path)
profile = load(config_path, pinned_profile_name)
batch = Batch(
    schema_version="askmill.batch.v2",
    requests=[Request.model_validate_json(p.read_bytes())
              for p in admitted_request_paths],
)
with Session(profile, store=workspace_receipts,
             lease=registry["lease_paths"]) as session:
    for request in batch.requests:
        result = session.run(request)
        # Retain the exact result/receipt, including incomplete/invalid output.
        # Consumer publication requires its independent post-output gates.
```

One session reuses the worker and leases; calls are serialized. Ollama residency
still follows the external service's policy. Observe provider load/cache
counters before labelling a route warm. Structured schemas require supported
local Ollama; never fall back to another model or provider.

## Output gates and independent expected evidence

Require `result.complete`, `result.response_validation.valid` and the exact
schema hash. Then independently check unique proposal IDs, supplied-ID
membership, bounded evidence hints and whole-source accounting: the union of
proposal and unresolved source IDs must equal the selected scope. Repeated
source IDs across different questions are allowed; duplicates within a list
are rejected. Preserve every known unbound dependency in unresolved items.

Schema validity cannot prove a question is grounded. Reject questions that
smuggle an unsupported premise, invented quantity, answer, legal conclusion,
client fact or citation. Never clip or repair output to admit it. Independently
reopen original pages/native parts to create expected-source assertions; the
proposal model's response cannot create gold answers. Query runs must bind
their actual query version, reading/rules, packet, question and result hashes.

Classify a failed real intent as source absence/unreviewedness, extraction loss,
missing structured relation, retrieval/permission/context loss, answer
coverage/entailment, numeric/formula error or presentation failure. Send one
owner fix packet with exact original/page/region/native/observed/result pins
and the affected regression. The owning engine fixes main, publishes an
immutable release, and receives explicit consumer acceptance before reuse.

## Cache, reruns and measurement

Include task kind, proposal contract, source scope, Map guidance, reading/rule
and customer-review pins in the request. The runner's identity includes the
actual prompt/schema/source metadata, model/revision/settings and runtime.
`source_id_bound_question_proposals` in the prompt distinguishes proposal
generation from answer evaluation. Keep independent expected assertions and
query-result pins separate; do not reuse a proposal as an answer.

Rerun only affected sources/intents/stages and regression controls after a
material version change. Replay retains the original attempt/session and
generation time; that time is not current replay latency. Count repeated real
inputs as performance observations only. Track schema, semantic, scope,
performance and presentation results separately, with actual monotonic times,
bytes, source/model/cache counts and declared inference/replay/warm/cold route.
With insufficient matched real samples or missing counters, latency thresholds
and p95 remain `not_established`. No synthetic fixture establishes current
real-source coverage, customer eligibility or answer accuracy.
