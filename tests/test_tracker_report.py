"""Retained-source reporting controls; mutations are not new source/accuracy cases."""

import copy
import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "tracker_report", ROOT / "tools/tracker_report.py"
)
reporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reporter)


@pytest.fixture
def retained():
    name = os.environ.get("ASKMILL_TRACKER_DESCRIPTOR")
    roots = os.environ.get("ASKMILL_TRACKER_ROOTS")
    if not name or not roots:
        pytest.skip("Supply authorized real retained receipt descriptor and roots")
    path = Path(name)
    before = path.read_bytes()
    yield json.loads(before), json.loads(Path(roots).read_bytes())
    assert path.read_bytes() == before


def project(retained):
    return reporter.project(*retained)


def mutated_native(retained, tmp_path, change):
    descriptor, roots = copy.deepcopy(retained)
    content = reporter.reference(descriptor["invocation"]["receipt"], roots)["content"]
    change(content)
    content["key"] = reporter.sha(
        reporter.canonical({k: content[k] for k in ["request", "profile", "runtime"]})
    )
    content["result"]["receipt_id"] = content["key"]
    wrapper = {"content": content, "sha256": reporter.sha(reporter.canonical(content))}
    raw = reporter.canonical(wrapper)
    (tmp_path / "control.json").write_bytes(raw)
    roots["control"] = str(tmp_path)
    descriptor["invocation"]["receipt"] = {
        "repository": "control",
        "path": "control.json",
        "sha256": reporter.sha(raw),
    }
    descriptor["invocation"].pop("settlement", None)
    return descriptor, roots


def test_retained_provider_counters_and_no_approval(retained):
    row = project(retained)[0]
    run = row["stages"]["askmill"]["runs"][0]
    assert run["model_calls"] == 1
    assert run["tokens"]["input"] > 0 and run["tokens"]["output"] > 0
    assert run["tokens"]["reserved_output"] >= run["tokens"]["output"]
    assert run["timings"]["model_seconds"] is not None
    assert run["timings"]["session_run_seconds"] >= run["timings"]["model_seconds"]
    assert run["timings"]["invocation_wall_seconds"] is None
    assert (
        run["review"]["status"] == "pending"
        and run["review"]["accepted_candidates"] is None
    )
    assert set(row["stages"]) == {"askmill"} and row["gold"] == {"kind": "none"}
    assert row["stages"]["askmill"]["timing"]["wall_seconds"] is None


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(unknown=True),
        lambda d: d["documents"][0].update(sha256="0" * 64),
        lambda d: d["invocation"]["receipt"].update(sha256="0" * 64),
        lambda d: d["invocation"]["receipt"].update(path="../outside.json"),
        lambda d: d["invocation"]["allocated_context"].update(
            revision_pointer="/allocated_context"
        ),
    ],
)
def test_pinned_scope_and_closed_descriptor_refusals(retained, mutation):
    descriptor, roots = copy.deepcopy(retained)
    mutation(descriptor)
    with pytest.raises((ValueError, KeyError)):
        reporter.project(descriptor, roots)


def test_unavailable_token_counter_stays_null(retained, tmp_path):
    def change(c):
        c["raw_response"].pop("prompt_eval_count")

    row = project(mutated_native(retained, tmp_path, change))[0]
    assert row["stages"]["askmill"]["runs"][0]["tokens"]["input"] is None


def test_boolean_provider_counter_is_not_integer(retained, tmp_path):
    def change(c):
        c["raw_response"]["prompt_eval_count"] = False

    with pytest.raises(ValueError, match="number or null"):
        project(mutated_native(retained, tmp_path, change))


def test_incomplete_control_is_not_promoted(retained, tmp_path):
    def change(c):
        c["result"]["complete"] = False
        c["result"]["status"] = "incomplete"
        c["raw_response"]["done_reason"] = "length"

    row = project(mutated_native(retained, tmp_path, change))[0]
    assert row["stages"]["askmill"]["status"] == "held"
    assert row["stages"]["askmill"]["runs"][0]["complete"] is False
    assert row["stages"]["askmill"]["runs"][0]["review"]["status"] == "pending"


def test_review_decision_must_be_in_bound_receipt(retained):
    descriptor, roots = copy.deepcopy(retained)
    descriptor["review"] = {
        "receipt": descriptor["invocation"]["receipt"],
        "pointer": "/content/result",
        "target_pointer": "/sha256",
    }
    with pytest.raises(ValueError):
        reporter.project(descriptor, roots)


def test_output_schema_identity_cannot_be_substituted(retained, tmp_path):
    def change(c):
        c["result"]["response_validation"]["schema_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="different response schema"):
        project(mutated_native(retained, tmp_path, change))


def test_replay_control_never_recounts_origin(retained, tmp_path):
    # A control mutation, NOT an actual replay invocation or registered ledger row.
    descriptor, roots = copy.deepcopy(retained)
    original = reporter.reference(descriptor["invocation"]["receipt"], roots)[
        "content"
    ]["result"]
    original["replayed"] = True
    raw = reporter.canonical(original)
    (tmp_path / "replay-control.json").write_bytes(raw)
    roots["control"] = str(tmp_path)
    descriptor["invocation"]["result"] = {
        "repository": "control",
        "path": "replay-control.json",
        "sha256": reporter.sha(raw),
    }
    descriptor["invocation"].pop("settlement")
    run = reporter.project(descriptor, roots)[0]["stages"]["askmill"]["runs"][0]
    assert run["model_calls"] == 0 and run["replayed"] is True
    assert run["tokens"]["input"] == run["tokens"]["output"] == 0
    assert (
        run["timings"]["model_seconds"] == 0
        and run["timings"]["session_run_seconds"] is None
    )
    assert run["replay_of_receipt"] == descriptor["invocation"]["receipt"]
    assert run["settlement"] is None


def test_cached_origin_settlement_cannot_claim_current_replay_cleanup(
    retained, tmp_path
):
    descriptor, roots = copy.deepcopy(retained)
    original = reporter.reference(descriptor["invocation"]["receipt"], roots)[
        "content"
    ]["result"]
    original["replayed"] = True
    raw = reporter.canonical(original)
    (tmp_path / "replay-control.json").write_bytes(raw)
    roots["control"] = str(tmp_path)
    descriptor["invocation"]["result"] = {
        "repository": "control",
        "path": "replay-control.json",
        "sha256": reporter.sha(raw),
    }
    with pytest.raises(ValueError, match="current replay cleanup"):
        reporter.project(descriptor, roots)


@pytest.mark.parametrize("status", ["accepted", "rejected", "partial"])
def test_caller_decision_is_reopened_from_pinned_review_not_completion(
    retained, tmp_path, status
):
    # Software-only review object. It is never registered as a real adjudication.
    descriptor, roots = copy.deepcopy(retained)
    review = {
        "target": descriptor["invocation"]["receipt"]["sha256"],
        "review": {
            "status": status,
            "reviewer": "software-control-only",
            "accepted_candidates": None,
            "rejected_candidates": None,
            "unreviewed_candidates": None,
        },
    }
    raw = reporter.canonical(review)
    (tmp_path / "review-control.json").write_bytes(raw)
    roots["control"] = str(tmp_path)
    descriptor["review"] = {
        "receipt": {
            "repository": "control",
            "path": "review-control.json",
            "sha256": reporter.sha(raw),
        },
        "pointer": "/review",
        "target_pointer": "/target",
    }
    row = reporter.project(descriptor, roots)[0]
    assert row["stages"]["askmill"]["runs"][0]["review"]["status"] == status
    assert "query" not in row["stages"] and row["gold"] == {"kind": "none"}


def test_extra_real_pdf_not_in_frozen_prompt_is_refused(retained):
    descriptor, roots = copy.deepcopy(retained)
    doc = copy.deepcopy(descriptor["documents"][0])
    original = reporter.reference(doc["original_receipt"], roots)
    other = reporter.pointer(original, "/contexts/0/original_sha256")
    assert other != doc["sha256"]
    doc.update(sha256=other, profile_id="CERC-04")
    doc["original_receipt"]["subject_pointer"] = "/contexts/0/original_sha256"
    descriptor["documents"].append(doc)
    with pytest.raises(ValueError, match="Frozen prompt source subjects"):
        reporter.project(descriptor, roots)


def test_structured_source_range_cannot_be_guessed(retained):
    descriptor, roots = copy.deepcopy(retained)
    descriptor["invocation"]["source_binding"]["prompt_json_byte_start"] += 1
    with pytest.raises(ValueError, match="Structured source (range|byte pin)"):
        reporter.project(descriptor, roots)


@pytest.mark.parametrize("conflict", [False, True])
def test_installed_map_global_invocation_dedup_control(retained, conflict):
    import subprocess

    python = os.environ.get("ASKMILL_TRACKER_MAP_PYTHON")
    if not python:
        pytest.skip("Supply pinned installed Map Python for integration control")
    row = project(retained)[0]
    second = copy.deepcopy(row)
    # Delivery/aggregation mutation only: not a claimed real two-PDF model run.
    doc = retained[0]["documents"][0]
    carrier = reporter.reference(doc["original_receipt"], retained[1])
    other = reporter.pointer(carrier, "/contexts/0/original_sha256")
    second["sha256"] = other
    for item in [row, second]:
        item["stages"]["askmill"]["runs"][0]["source_document_sha256s"] = sorted(
            [row["sha256"], other]
        )
    if conflict:
        second["stages"]["askmill"]["runs"][0]["tokens"]["input"] += 1
    script = "import json,sys; from powerlex_map.tracker_ledger import model_totals; print(json.dumps(model_totals(json.load(sys.stdin))))"
    run = subprocess.run(
        [python, "-c", script],
        input=json.dumps([row, second]),
        capture_output=True,
        text=True,
        timeout=15,
    )
    if conflict:
        assert run.returncode != 0 and "conflicting metrics" in run.stderr
    else:
        assert run.returncode == 0, run.stderr
        totals = json.loads(run.stdout)
        assert (
            totals["unique_invocations"] == 1
            and totals["fresh_model_calls_observed"] == 1
        )
        assert (
            totals["observed_input_tokens"]
            == row["stages"]["askmill"]["runs"][0]["tokens"]["input"]
        )
        assert totals["source_or_domain_acceptance_inferred"] is False
