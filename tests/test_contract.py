import pytest
from pydantic import ValidationError

from askmill import Profile, Request


@pytest.mark.parametrize(
    "data",
    [
        {"prompt": " "},
        {"prompt": "x", "max_tokens": 0},
        {"prompt": "x", "timeout": float("nan")},
        {"prompt": "x", "unknown": 1},
        {"prompt": "x", "max_tokens": True},
    ],
)
def test_invalid_requests(data):
    with pytest.raises(ValidationError):
        Request(**data)


def test_unsupported_ownership():
    with pytest.raises(ValidationError):
        Profile(
            provider="ollama",
            model="x",
            revision="x",
            capabilities=["text"],
            base_url="http://127.0.0.1:11434",
            ownership="worker",
        )


def test_contract_roundtrip():
    request = Request(prompt="Read the printed qualifier.", sources=[])
    assert Request.model_validate_json(request.model_dump_json()) == request
