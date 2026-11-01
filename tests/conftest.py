import sys
from askmill.profiles import model_revision
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
        "runtime": "test-version",
        "remote": False,
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path == "/api/version":
                return self.reply({"version": state["runtime"]})
            self.reply({"models": [{"name": "fixture:1", "digest": state["revision"]}]})

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/api/show":
                return self.reply(
                    {
                        "capabilities": ["completion", "vision"],
                        "remote_host": "cloud.example" if state["remote"] else None,
                    }
                )
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


@pytest.fixture
def mlx_profile(tmp_path, monkeypatch):
    modules = tmp_path / "modules"
    (modules / "mlx").mkdir(parents=True)
    (modules / "mlx" / "__init__.py").write_text("")
    (modules / "mlx" / "core.py").write_text("""
class metal:
    @staticmethod
    def is_available(): return True
gpu = 'gpu'
def set_default_device(x): pass
def default_device(): return gpu
def get_peak_memory(): return 100
def clear_cache(): pass
""")
    (modules / "mlx_vlm.py").write_text("""
import os,time,json,hashlib
from pathlib import Path
from types import SimpleNamespace
def load(path):
    assert os.environ['HF_HUB_OFFLINE']=='1'
    p=Path(os.environ['LOAD_COUNTER'])
    p.write_text(p.read_text()+'load\\n' if p.exists() else 'load\\n')
    return object(),SimpleNamespace(apply_chat_template=lambda messages,**k: messages[0]['content'][-1]['text'])
def generate(*args,**kwargs):
    if os.environ.get('SLOW_FIXTURE'): time.sleep(5)
    if os.environ.get('GENERATION_LOG'):
        row={'prompt':args[2], 'images':[hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in kwargs.get('image') or []], 'max_tokens':kwargs['max_tokens']}
        with open(os.environ['GENERATION_LOG'],'a') as handle: handle.write(json.dumps(row)+'\\n')
    return SimpleNamespace(text='42',generation_tokens=int(os.environ.get('GENERATED_TOKENS','2')))
""")
    monkeypatch.setenv("PYTHONPATH", str(modules))
    monkeypatch.setenv("LOAD_COUNTER", str(tmp_path / "loads"))
    cache = tmp_path / "model"
    cache.mkdir()
    (cache / "config.json").write_text("{}")
    return Profile(
        provider="mlx-vlm",
        model="synthetic",
        revision=model_revision(cache),
        model_path=str(cache),
        python=sys.executable,
        ownership="worker",
        capabilities=["text", "vision"],
    )
