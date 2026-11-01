import json
import pytest
from askmill import Request
from askmill.runner import RunError, Session


def test_warm_session_replay_after_restart(endpoint, tmp_path):
    profile, state = endpoint
    args = profile, tmp_path / "receipts", tmp_path / "gpu.lock"
    with Session(*args) as session:
        pid = session.worker.pid
        first = session.run(Request(prompt="First crop"))
        second = session.run(Request(prompt="Second crop"))
        assert session.worker.pid == pid
        assert first.receipt_id != second.receipt_id
    with Session(*args) as session:
        replay = session.run(Request(prompt="First crop"))
        assert replay.replayed and replay.attempt_id == first.attempt_id
        session.run(Request(prompt="Changed crop"))
    assert len(state["calls"]) == 3
    assert all(path == "/api/chat" for path, _ in state["calls"])


def test_incomplete_and_integrity(endpoint, tmp_path):
    profile, state = endpoint
    state["complete"] = False
    with Session(profile, tmp_path / "r", tmp_path / "lock") as session:
        request = Request(prompt="x")
        result = session.run(request)
        assert result.status == "incomplete" and not result.complete
        receipt = tmp_path / "r" / (result.receipt_id + ".json")
        data = json.loads(receipt.read_text())
        data["content"]["result"]["text"] = "tampered"
        receipt.write_text(json.dumps(data))
        with pytest.raises(RunError, match="integrity"):
            session.run(request)


def test_timeout_quarantines_external_lease(endpoint, tmp_path):
    profile, state = endpoint
    state["delay"] = 0.4
    args = profile, tmp_path / "r", tmp_path / "lock"
    with Session(*args) as session:
        with pytest.raises(RunError) as error:
            session.run(Request(prompt="slow", timeout=0.05))
        assert error.value.status == "timeout"
        assert session.worker is None
    with pytest.raises(RunError) as error, Session(*args):
        pass
    assert error.value.status == "cleanup_uncertain"
    # A fresh client can still use the externally owned server.
    import urllib.request

    assert urllib.request.urlopen(profile.base_url + "/api/tags").status == 200


def test_device_lock_and_wrong_digest(endpoint, tmp_path):
    profile, state = endpoint
    with Session(profile, tmp_path / "r", tmp_path / "lock"):
        with pytest.raises(RunError) as error:
            with Session(profile, tmp_path / "other", tmp_path / "lock"):
                pass
        assert error.value.status == "busy"
    profile = profile.model_copy(update={"revision": "wrong"})
    with pytest.raises(RunError) as error:
        with Session(profile, tmp_path / "r", tmp_path / "lock"):
            pass
    assert error.value.status == "model_mismatch"
    assert not state["calls"]


def test_freeze_image_and_output_candidates(endpoint, tmp_path):
    profile, state = endpoint
    image = tmp_path / "crop.png"
    image.write_bytes(b"synthetic image byte fixture")
    with Session(profile, tmp_path / "r", tmp_path / "lock") as session:
        request = Request(prompt="Read", images=[str(image)])
        a = session.run(request)
        image.write_bytes(b"changed fixture")
        b = session.run(request)
    assert a.receipt_id != b.receipt_id
    assert a.domain_acceptance == "unverified"
    assert (
        state["calls"][0][1]["messages"][0]["images"]
        != state["calls"][1][1]["messages"][0]["images"]
    )


def test_tag_change_during_generation_never_commits(endpoint, tmp_path):
    profile, state = endpoint
    state["mutate_revision"] = True
    with Session(profile, tmp_path / "r", tmp_path / "lock") as session:
        with pytest.raises(RunError) as error:
            session.run(Request(prompt="candidate with changed model"))
        assert error.value.status == "model_mismatch"
    assert not list((tmp_path / "r").glob("*.json"))
    assert (tmp_path / "lock.unsettled").exists()
