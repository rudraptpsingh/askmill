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
