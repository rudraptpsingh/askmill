"""Exercise the real persistent worker with synthetic MLX modules, no model weights."""

import sys
from pathlib import Path

import pytest

from askmill import Profile, Request
from askmill.profiles import model_revision
from askmill.runner import RunError, Session


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
import os,time
from pathlib import Path
from types import SimpleNamespace
def load(path):
    assert os.environ['HF_HUB_OFFLINE']=='1'
    p=Path(os.environ['LOAD_COUNTER'])
    p.write_text(p.read_text()+'load\\n' if p.exists() else 'load\\n')
    return object(),SimpleNamespace(apply_chat_template=lambda *a,**k: 'template')
def generate(*args,**kwargs):
    if os.environ.get('SLOW_FIXTURE'): time.sleep(5)
    return SimpleNamespace(text='42',generation_tokens=2)
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


def test_batch_loads_once_and_replays_without_generation(mlx_profile, tmp_path):
    args = mlx_profile, tmp_path / "receipts", tmp_path / "lease"
    with Session(*args) as session:
        a = session.run(Request(prompt="first"))
        session.run(Request(prompt="second"))
    with Session(*args) as session:
        assert session.run(Request(prompt="first")).replayed
    assert (tmp_path / "loads").read_text().splitlines() == ["load"]
    assert a.text == "42"


def test_owned_timeout_stops_worker_and_releases_lease(
    mlx_profile, tmp_path, monkeypatch
):
    monkeypatch.setenv("SLOW_FIXTURE", "1")
    args = mlx_profile, tmp_path / "receipts", tmp_path / "lease"
    with Session(*args) as session:
        worker = session.worker
        with pytest.raises(RunError):
            session.run(Request(prompt="slow", timeout=0.05))
        assert worker.poll() is not None
    monkeypatch.delenv("SLOW_FIXTURE")
    with Session(*args) as session:
        assert session.run(Request(prompt="retry")).text == "42"


def test_model_mutation_rejected_before_load(mlx_profile, tmp_path):
    Path(mlx_profile.model_path, "config.json").write_text("changed")
    with pytest.raises(RunError) as error:
        with Session(mlx_profile, tmp_path / "r", tmp_path / "lease"):
            pass
    assert error.value.status == "model_mismatch"
    assert not (tmp_path / "loads").exists()


def test_pdf2data_session_shim_preserves_generation_boundary(mlx_profile, tmp_path):
    from askmill.pdf2data import MLXSession

    profile = {
        "provider": "mlx-vlm",
        "model": mlx_profile.model,
        "python": mlx_profile.python,
        "model_path": mlx_profile.model_path,
    }
    before = dict(profile)
    session = MLXSession(profile, store=tmp_path / "r", lease=tmp_path / "lock")
    try:
        first = session.generate("first", (), 64, 10)
        second = session.generate("second", (), 64, 10)
    finally:
        session.close()
    assert profile == before
    assert first["text"] == second["text"] == "42"
    assert first["complete"] and first["generated_tokens"] == 2
    assert (tmp_path / "loads").read_text().splitlines() == ["load"]


def test_parent_crash_preserves_commit_and_worker_lease(
    mlx_profile, tmp_path, monkeypatch
):
    import subprocess
    import time
    from askmill.runner import RunError

    # Signal from inside generation, so the parent dies after item one committed
    # and while item two is running.
    module = tmp_path / "modules" / "mlx_vlm.py"
    code = module.read_text()
    code = code.replace(
        "lambda *a,**k: 'template'",
        "lambda messages,**k: messages[0]['content'][-1]['text']",
    )
    code = code.replace(
        "if os.environ.get('SLOW_FIXTURE'): time.sleep(5)",
        "if args[2]=='slow':\n        Path(os.environ['SECOND_STARTED']).write_text('started')\n        time.sleep(.5)",
    )
    module.write_text(code)
    monkeypatch.setenv("SECOND_STARTED", str(tmp_path / "started"))
    store, lease = str(tmp_path / "r"), str(tmp_path / "lease")
    script = """
import json,sys
from askmill import Profile, Request
from askmill.runner import Session
with Session(Profile.model_validate_json(sys.argv[1]),sys.argv[2],sys.argv[3]) as session:
    session.run(Request(prompt='first'))
    session.run(Request(prompt='slow'))
"""
    child = subprocess.Popen(
        [sys.executable, "-c", script, mlx_profile.model_dump_json(), store, lease],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        while not (tmp_path / "started").exists():
            assert time.monotonic() < deadline
            assert child.poll() is None
            time.sleep(0.01)
        child.kill()
        child.wait()
        assert len(list((tmp_path / "r").glob("*.json"))) == 1
        with pytest.raises(RunError) as error:
            with Session(mlx_profile, store, lease):
                pass
        assert error.value.status == "busy"  # inherited by the live worker
        # Worker finishes its bounded fixture, sees EOF and releases its lock.
        deadline = time.monotonic() + 10
        while True:
            try:
                recovered = Session(mlx_profile, store, lease).__enter__()
                break
            except RunError as error:
                assert error.status == "busy" and time.monotonic() < deadline
                time.sleep(0.05)
        try:
            assert recovered.run(Request(prompt="first")).replayed
            assert not recovered.run(Request(prompt="slow")).replayed
        finally:
            recovered.close()
        assert len(list((tmp_path / "r").glob("*.json"))) == 2
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
