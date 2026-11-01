import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from askmill import Profile


@pytest.fixture
def endpoint():
    state = {
        "calls": [],
        "delay": 0,
        "complete": True,
        "revision": "sha256:test",
        "mutate_revision": False,
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.reply({"models": [{"name": "fixture:1", "digest": state["revision"]}]})

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["calls"].append((self.path, data))
            if state["mutate_revision"]:
                state["revision"] = "changed"
            time.sleep(state["delay"])
            self.reply(
                {
                    "model": "fixture:1",
                    "done": True,
                    "done_reason": "stop" if state["complete"] else "length",
                    "eval_count": 1,
                    "message": {"content": "candidate"},
                }
            )

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
    profile = Profile(
        provider="ollama",
        model="fixture:1",
        revision="sha256:test",
        capabilities=["text", "vision"],
        base_url=f"http://127.0.0.1:{server.server_port}",
    )
    yield profile, state
    server.shutdown()
    server.server_close()
    thread.join()
