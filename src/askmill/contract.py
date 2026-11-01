"""Versioned portable contract. Domain acceptance belongs to the consumer."""

import math
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
    model_serializer,
)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class GenerationSettings(Strict):
    temperature: float = Field(default=0.0, ge=0, le=2)
    top_p: float | None = Field(default=None, gt=0, le=1)
    top_k: int | None = Field(default=None, ge=0, le=200)
    context_tokens: int | None = Field(default=None, ge=512, le=32768)
    thinking: bool | Literal["low", "medium", "high", "xhigh"] | None = False
    mlx_template: Literal["processor", "model"] = "processor"


class Profile(Strict):
    schema_version: Literal["askmill.profile.v1", "askmill.profile.v2"] = (
        "askmill.profile.v1"
    )
    provider: Literal["mlx-vlm", "ollama", "openai-compatible"]
    model: str = Field(min_length=1, max_length=300)
    revision: str = Field(min_length=1, max_length=300)
    capabilities: list[Literal["text", "vision"]] = Field(min_length=1)
    python: str | None = None
    model_path: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    ownership: Literal["external", "worker"] = "external"
    generation: GenerationSettings | None = None

    @model_serializer(mode="wrap")
    def serialize_profile(self, handler):
        data = handler(self)
        if self.schema_version == "askmill.profile.v1":
            data.pop("generation", None)
        return data

    @model_validator(mode="after")
    def supported(self):
        if self.generation and self.schema_version != "askmill.profile.v2":
            raise ValueError("Generation settings require askmill.profile.v2")
        if self.generation and self.provider == "mlx-vlm":
            if self.generation.context_tokens is not None:
                raise ValueError(
                    "Explicit context allocation is supported by Ollama profiles only"
                )
            if isinstance(self.generation.thinking, str):
                raise ValueError("MLX thinking requires a boolean or null")
        if (
            self.generation
            and self.provider != "mlx-vlm"
            and self.generation.mlx_template != "processor"
        ):
            raise ValueError("MLX templates require the MLX provider")
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


class ResponseSchema(Strict):
    schema_version: Literal["askmill.response-schema.v1"] = "askmill.response-schema.v1"
    document: dict
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def checked(self):
        from .structured import check_schema, schema_digest

        check_schema(self.document)
        if schema_digest(self.document) != self.sha256:
            raise ValueError("Response schema SHA256 mismatch")
        return self

    @classmethod
    def from_schema(cls, document):
        from .structured import check_schema, schema_digest

        check_schema(document)
        return cls(document=document, sha256=schema_digest(document))


class Request(Strict):
    schema_version: Literal["askmill.request.v1", "askmill.request.v2"] = (
        "askmill.request.v1"
    )
    prompt: str = Field(min_length=1, max_length=200000)
    images: list[str] = Field(default_factory=list, max_length=8)
    max_tokens: int = Field(default=2048, ge=1, le=16384)
    timeout: float = Field(default=180.0, gt=0, le=3600)
    sources: list[Source] = Field(default_factory=list)
    response_schema: ResponseSchema | None = None

    @model_serializer(mode="wrap")
    def serialize_request(self, handler):
        data = handler(self)
        if self.schema_version == "askmill.request.v1":
            data.pop("response_schema", None)
        return data

    @model_validator(mode="after")
    def versioned_response(self):
        if (self.schema_version == "askmill.request.v2") != (
            self.response_schema is not None
        ):
            raise ValueError(
                "Response schema requires explicit request v2; v2 requires a schema"
            )
        return self

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


class ResponseValidation(Strict):
    schema_version: Literal["askmill.response-validation.v1"] = (
        "askmill.response-validation.v1"
    )
    schema_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    valid: bool
    errors: list[str] = Field(max_length=16)


class Result(Strict):
    schema_version: Literal["askmill.result.v1", "askmill.result.v2"] = (
        "askmill.result.v1"
    )
    status: Literal["completed", "incomplete", "schema_invalid"]
    text: str
    complete: bool
    model: str
    revision: str
    generated_tokens: int | None = None
    seconds: float
    runtime: dict[str, str] = Field(default_factory=dict)
    device: str | None = None
    peak_device_memory_bytes: int | None = None
    receipt_id: str
    attempt_id: str
    session_id: str
    replayed: bool = False
    domain_acceptance: Literal["unverified"] = "unverified"
    response_validation: ResponseValidation | None = None

    @model_serializer(mode="wrap")
    def serialize_result(self, handler):
        data = handler(self)
        if self.schema_version == "askmill.result.v1":
            data.pop("response_validation", None)
        return data

    @model_validator(mode="after")
    def versioned_validation(self):
        if (self.schema_version == "askmill.result.v2") != (
            self.response_validation is not None
        ):
            raise ValueError("Result v2 requires response validation")
        expected = (
            "incomplete"
            if not self.complete
            else (
                "schema_invalid"
                if self.response_validation and not self.response_validation.valid
                else "completed"
            )
        )
        if self.status != expected:
            raise ValueError("Status differs from completion/schema validity")
        return self


class Batch(Strict):
    schema_version: Literal["askmill.batch.v1", "askmill.batch.v2"] = "askmill.batch.v1"
    requests: list[Request] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def bounded(self):
        if self.schema_version == "askmill.batch.v1" and any(
            item.schema_version != "askmill.request.v1" for item in self.requests
        ):
            raise ValueError("Request v2 requires batch v2")
        if sum(item.timeout for item in self.requests) > 3600:
            raise ValueError("Total batch generation deadlines exceed one hour")
        return self
