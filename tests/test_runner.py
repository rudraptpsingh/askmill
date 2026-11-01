import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
import pytest

from askmill import Profile, Request
from askmill.runner import RunError, Session


@pytest.fixture
def endpoint():
    state = {"calls": [], "delay": 0, "complete": True}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            self.reply({"models": [{"name": "fixture:1", "digest": "sha256:test"}]})
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["calls"].append((self.path, data))
            time.sleep(state["delay"])
            self.reply({"model": "fixture:1", "done": True,
                        "done_reason": "stop" if state["complete"] else "length",
                        "eval_count": 1, "message": {"content": "candidate"}})
        def reply(self, data):
            self.send_response(200)
            self.end_headers()
            try:
                self.wfile.write(json.dumps(data).encode())
            except BrokenPipeError:
                pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    profile = Profile(provider="ollama", model="fixture:1", revision="sha256:test",
                      capabilities=["text", "vision"], base_url=f"http://127.0.0.1:{server.server_port}")
    yield profile, state
    server.shutdown()
    server.server_close()
    thread.join()


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
    state["delay"] = .4
    args = profile, tmp_path / "r", tmp_path / "lock"
    with Session(*args) as session:
        with pytest.raises(RunError) as error:
            session.run(Request(prompt="slow", timeout=.05))
        assert error.value.status == "timeout"
        assert session.worker is None
    with pytest.raises(RunError) as error:
        with Session(*args):
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
    assert state["calls"][0][1]["messages"][0]["images"] != state["calls"][1][1]["messages"][0]["images"]
