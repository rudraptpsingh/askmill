"""Versioned portable contract. Domain acceptance belongs to the consumer."""

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Profile(Strict):
    schema_version: Literal["askmill.profile.v1"] = "askmill.profile.v1"
    provider: Literal["mlx-vlm", "ollama", "openai-compatible"]
    model: str = Field(min_length=1, max_length=300)
    revision: str = Field(min_length=1, max_length=300)
    capabilities: list[Literal["text", "vision"]] = Field(min_length=1)
    python: str | None = None
    model_path: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    ownership: Literal["external", "worker"] = "external"

    @model_validator(mode="after")
    def supported(self):
        if self.provider == "mlx-vlm":
            if not self.python or not self.model_path or self.ownership != "worker":
                raise ValueError("MLX requires python, model_path and worker ownership")
        elif not self.base_url or self.ownership != "external":
            raise ValueError(
                "HTTP providers require base_url and external ownership in v0"
            )
        return self


class Source(Strict):
    id: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Request(Strict):
    schema_version: Literal["askmill.request.v1"] = "askmill.request.v1"
    prompt: str = Field(min_length=1, max_length=200000)
    images: list[str] = Field(default_factory=list, max_length=8)
    max_tokens: int = Field(default=2048, ge=1, le=16384)
    timeout: float = Field(default=180.0, gt=0, le=3600)
    sources: list[Source] = Field(default_factory=list)

    @field_validator("prompt")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Prompt must contain text")
        return value

    @field_validator("timeout")
    @classmethod
    def finite(cls, value):
        if not math.isfinite(value):
            raise ValueError("Timeout must be finite")
        return value


class Result(Strict):
    schema_version: Literal["askmill.result.v1"] = "askmill.result.v1"
    status: Literal["completed", "incomplete"]
    text: str
    complete: bool
    model: str
    revision: str
    generated_tokens: int | None = None
    seconds: float
    receipt_id: str
    attempt_id: str
    replayed: bool = False
    domain_acceptance: Literal["unverified"] = "unverified"
