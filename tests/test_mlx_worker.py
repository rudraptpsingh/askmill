"""Exercise the real persistent worker with synthetic MLX modules, no model weights."""

import sys
from pathlib import Path

import pytest

from askmill import Request
from askmill.runner import RunError, Session


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
            committed = next((tmp_path / "r").glob("*.json"))
            original = committed.read_bytes()
            # A committed item from a dead parent has no verified settlement.
            # Preserve it, but never promote result existence into safe replay.
            with pytest.raises(RunError, match="no verified settlement"):
                recovered.run(Request(prompt="first"))
            assert committed.read_bytes() == original
            assert not recovered.run(Request(prompt="slow")).replayed
        finally:
            recovered.close()
        assert len(list((tmp_path / "r").glob("*.json"))) == 2
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


def test_cli_interrupt_reports_cancelled_and_reaps_worker(
    mlx_profile, tmp_path, monkeypatch
):
    import json
    import signal
    import subprocess
    import time

    monkeypatch.setenv("SLOW_FIXTURE", "1")
    config = tmp_path / "profiles.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": "askmill.profiles.v1",
                "profiles": {"test": mlx_profile.model_dump()},
            }
        )
    )
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("slow")
    child = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "askmill.cli",
            "--config",
            str(config),
            "--store",
            str(tmp_path / "r"),
            "--lease",
            str(tmp_path / "lock"),
            "run",
            "--profile",
            "test",
            "--input",
            str(prompt),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10
        while not (tmp_path / "loads").exists():
            assert child.poll() is None and time.monotonic() < deadline
            time.sleep(0.01)
        child.send_signal(signal.SIGINT)
        stdout, stderr = child.communicate(timeout=10)
        assert child.returncode == 130, (stdout, stderr)
        assert json.loads(stdout)["status"] == "cancelled"
        settlements = list((tmp_path / "r/settlements").glob("*.json"))
        assert json.loads(settlements[0].read_text())["content"]["worker_reaped"]
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
