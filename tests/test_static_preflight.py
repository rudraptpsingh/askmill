"""Static qualification admission controls; no model or document fixtures."""

import hashlib
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def qualifier(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    spec = importlib.util.spec_from_file_location(
        "qwen_static", ROOT / "tools/qwen35_static_preflight.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop("capacity_preflight", None)


def test_asset_pin_mismatch_refused(qualifier, tmp_path):
    asset = tmp_path / "asset"
    asset.write_bytes(b"bounded software control")
    with pytest.raises(ValueError, match="pin mismatch"):
        qualifier.verify(
            {"path": str(asset), "sha256": "0" * 64, "bytes": asset.stat().st_size}
        )


def test_asset_size_pin_checked(qualifier, tmp_path):
    asset = tmp_path / "asset"
    raw = b"bounded software control"
    asset.write_bytes(raw)
    with pytest.raises(ValueError, match="pin mismatch"):
        qualifier.verify(
            {
                "path": str(asset),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw) + 1,
            }
        )


def test_asset_limit_checked_before_open(qualifier, tmp_path):
    asset = tmp_path / "asset"
    with asset.open("wb") as handle:
        handle.truncate(qualifier.PIN_LIMIT + 1)
    with pytest.raises(ValueError, match="byte limit"):
        qualifier.verify(
            {"path": str(asset), "sha256": "0" * 64, "bytes": asset.stat().st_size}
        )


def test_wrong_plan_pin_never_creates_output(qualifier, tmp_path):
    plan = tmp_path / "plan.json"
    plan.write_text("{}")
    with pytest.raises(ValueError, match="Plan checksum mismatch"):
        qualifier.qualify(plan, "0" * 64, tmp_path / "qualification")
    assert not (tmp_path / "qualification").exists()
