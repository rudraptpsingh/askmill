import json
import pytest
from pydantic import ValidationError

from askmill import Profile, Request
from askmill.runner import Session, RunError


def configured(profile, **kwargs):
    return Profile.model_validate(
        {
            **profile.model_dump(),
            "schema_version": "askmill.profile.v2",
            "generation": kwargs,
        }
    )


def test_v1_payload_unchanged(endpoint, tmp_path):
    profile, state = endpoint
    with Session(profile, tmp_path / "r", tmp_path / "l") as session:
        session.run(Request(prompt="old", max_tokens=64))
    payload = state["calls"][0][1]
    assert payload["think"] is False
    assert payload["options"] == {"temperature": 0, "num_predict": 64}


def test_v2_options_and_receipt_identity(endpoint, tmp_path):
    profile, state = endpoint
    profile = configured(
        profile,
        thinking=True,
        context_tokens=8192,
        temperature=0.6,
        top_p=0.95,
        top_k=20,
    )
    with Session(profile, tmp_path / "r", tmp_path / "l") as session:
        first = session.run(Request(prompt="same", max_tokens=256))
    payload = state["calls"][0][1]
    assert payload["think"] is True
    assert payload["options"] == {
        "temperature": 0.6,
        "num_predict": 256,
        "num_ctx": 8192,
        "top_p": 0.95,
        "top_k": 20,
    }
    other = configured(profile, thinking=False, context_tokens=4096)
    with Session(other, tmp_path / "r", tmp_path / "l") as session:
        second = session.run(Request(prompt="same", max_tokens=256))
    assert first.receipt_id != second.receipt_id and not second.replayed
    content = json.loads((tmp_path / "r" / (first.receipt_id + ".json")).read_text())[
        "content"
    ]
    assert content["profile"]["generation"]["thinking"] is True


def test_invalid_generation_profiles(endpoint, mlx_profile):
    profile, state = endpoint
    with pytest.raises(ValidationError):
        Profile.model_validate(
            {**profile.model_dump(), "generation": {"thinking": True}}
        )
    with pytest.raises(ValidationError):
        configured(profile, context_tokens=1000000)
    with pytest.raises(ValidationError):
        configured(mlx_profile, thinking="high")
    with pytest.raises(ValidationError):
        configured(mlx_profile, context_tokens=8192)


def test_thinking_levels_rejected_before_input(endpoint, tmp_path):
    profile, state = endpoint
    profile = configured(profile, thinking="high")
    state["thinking_values"] = [False, True]
    with pytest.raises(RunError) as error:
        with Session(profile, tmp_path / "r", tmp_path / "l"):
            pass
    assert error.value.status == "unsupported" and not state["calls"]


def test_named_reasoning_level_and_reasoning_only_truncation(endpoint, tmp_path):
    profile, state = endpoint
    profile = configured(profile, thinking="low")
    state.update(answer="", reasoning="partial internal work", complete=False)
    with Session(profile, tmp_path / "r", tmp_path / "l") as session:
        result = session.run(Request(prompt="reasoning task"))
    assert result.status == "incomplete" and result.text == "" and not result.complete
    assert state["calls"][0][1]["think"] == "low"
    assert not (tmp_path / "l.unsettled").exists()


def test_mlx_model_template_is_used(mlx_profile, tmp_path, monkeypatch):
    module = tmp_path / "modules/mlx_vlm.py"
    module.write_text(
        module.read_text()
        + """
import sys,types,json
__path__=[]
utils=types.ModuleType('mlx_vlm.prompt_utils')
def apply_chat_template(processor,config,prompt,num_images=0,**kwargs):
    from pathlib import Path
    Path(os.environ['TEMPLATE_LOG']).write_text(json.dumps({'num_images':num_images,**kwargs}))
    return 'special:'+prompt
utils.apply_chat_template=apply_chat_template
sys.modules['mlx_vlm.prompt_utils']=utils
"""
    )
    monkeypatch.setenv("TEMPLATE_LOG", str(tmp_path / "template.json"))
    profile = configured(
        mlx_profile, mlx_template="model", thinking=False, temperature=0.2
    )
    image = tmp_path / "image.png"
    image.write_bytes(b"pixels")
    with Session(profile, tmp_path / "r", tmp_path / "l") as session:
        assert session.run(Request(prompt="OCR:", images=[str(image)])).text == "42"
    assert json.loads((tmp_path / "template.json").read_text()) == {
        "num_images": 1,
        "enable_thinking": False,
    }


def test_v1_serialization_retains_original_wire_keys(endpoint):
    profile, _ = endpoint
    assert "generation" not in profile.model_dump()
    assert "generation" not in json.loads(profile.model_dump_json())


def test_installed_cli_version_and_both_profile_versions(endpoint, tmp_path):
    import subprocess
    import sys

    profile, _ = endpoint
    newer = configured(profile, thinking=True, context_tokens=8192)
    config = tmp_path / "profiles.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": "askmill.profiles.v1",
                "profiles": {"old": profile.model_dump(), "new": newer.model_dump()},
            }
        )
    )
    version = subprocess.run(
        [sys.executable, "-m", "askmill.cli", "--version"],
        capture_output=True,
        text=True,
    )
    assert version.returncode == 0 and version.stdout.startswith("askmill ")
    installed = version.stdout.strip().split(" ", 1)[1]
    for name in ["old", "new"]:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "askmill.cli",
                "--config",
                str(config),
                "doctor",
                "--profile",
                name,
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout
        data = json.loads(result.stdout)
        assert (
            data["status"] == "configuration_valid"
            and data["runner_version"] == installed
        )
