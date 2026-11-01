# Adapted from PDF2Data (MIT). See THIRD_PARTY_NOTICES.md and LICENSE.
"""Named local model references and one transport contract; no agent framework."""

import base64
import ipaddress
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def validate(profile):
    if profile.get("provider") not in ("ollama", "openai-compatible", "mlx-vlm"):
        raise ValueError("Unknown local model provider")
    if not isinstance(profile.get("model"), str) or not profile["model"].strip():
        raise ValueError("A model reference is required")
    if profile["provider"] == "mlx-vlm":
        if (
            not Path(profile["python"]).is_file()
            or not Path(profile["model_path"]).is_dir()
        ):
            raise ValueError(
                "Configure an existing Python runtime and cached MLX model directory"
            )
    else:
        url = urllib.parse.urlsplit(profile["base_url"])
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError(
                "Use a local HTTP base URL without credentials, query or fragment"
            )
        try:
            local = (
                url.hostname == "localhost"
                or ipaddress.ip_address(url.hostname).is_loopback
                or ipaddress.ip_address(url.hostname).is_private
            )
        except ValueError:
            local = url.hostname == "localhost"
        if not local:
            raise ValueError("This adapter accepts localhost or private IP endpoints")
        env = profile.get("api_key_env")
        if env and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env):
            raise ValueError("Use an environment variable name for the API key")
    return profile


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError(
            "Local model endpoint redirected; configure its final local URL"
        )


def request(profile, suffix, payload=None, timeout=180):
    headers = {"Content-Type": "application/json"}
    if profile.get("api_key_env"):
        key = os.environ.get(profile["api_key_env"])
        if not key:
            raise ValueError("Configured API-key environment variable is unset")
        headers["Authorization"] = "Bearer " + key
    url = profile["base_url"].rstrip("/") + "/" + suffix.lstrip("/")
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers=headers,
    )
    try:
        with urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect
        ).open(req, timeout=timeout) as response:
            raw = response.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError("Local model response exceeds 16 MB; narrow the request")
        return json.loads(raw)
    except urllib.error.HTTPError as error:
        raise ValueError(
            "Local model HTTP "
            + str(error.code)
            + "; check model availability and endpoint settings"
        ) from None
    except (urllib.error.URLError, TimeoutError) as error:
        raise ValueError(
            "Cannot reach local model endpoint: "
            + str(error.reason if hasattr(error, "reason") else error)
        ) from None


def image_data(paths):
    images = []
    if len(paths) > 8:
        raise ValueError("Use at most 8 page images per request")
    for path in paths:
        path = Path(path).resolve()
        mime = mimetypes.guess_type(path.name)[0]
        if mime not in ("image/png", "image/jpeg", "image/webp"):
            raise ValueError(
                "Use PNG, JPEG or WebP page images; parse PDFs through PDF2Data first"
            )
        data = path.read_bytes()
        if len(data) > 16 * 1024 * 1024:
            raise ValueError("Page image exceeds 16 MB")
        images.append((mime, base64.b64encode(data).decode()))
    return images


class Session:
    def __init__(self, profile):
        self.profile = validate(profile)
        self.model = None
        self.processor = None

    def close(self):
        if self.model is not None:
            self.model = None
            self.processor = None
            import gc

            import mlx.core as mx

            gc.collect()
            mx.clear_cache()

    def generate(self, prompt, images=(), max_tokens=2048, timeout=180):
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 200000:
            raise ValueError("Provide a prompt of 1..200000 characters")
        if not 1 <= max_tokens <= 16384:
            raise ValueError("Use max tokens 1..16384")
        profile = self.profile
        image_values = image_data(images)
        started = time.perf_counter()
        if profile["provider"] == "mlx-vlm":
            # Core installs can reference an existing MLX environment without
            # installing any model dependencies in PDF2Data's own environment.
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            import mlx.core as mx

            if not mx.metal.is_available():
                raise ValueError("Metal GPU unavailable; no silent CPU fallback")
            mx.set_default_device(mx.gpu)
            from mlx_vlm import generate, load

            if self.model is None:
                self.model, self.processor = load(profile["model_path"])
            content = [{"type": "image"} for _ in images] + [
                {"type": "text", "text": prompt}
            ]
            template = self.processor.apply_chat_template(
                [{"role": "user", "content": content}],
                tokenize=False,
                add_generation_prompt=True,
            )
            result = generate(
                self.model,
                self.processor,
                template,
                image=[str(p) for p in images] if images else None,
                max_tokens=max_tokens,
                temp=0.0,
                verbose=False,
            )
            tokens = getattr(result, "generation_tokens", None)
            return dict(
                text=result.text.strip(),
                generated_tokens=tokens,
                complete=tokens is not None and tokens < max_tokens,
                device=str(mx.default_device()),
                peak_device_memory_bytes=mx.get_peak_memory(),
                seconds=time.perf_counter() - started,
                model=profile["model"],
            )
        if profile["provider"] == "ollama":
            message = {"role": "user", "content": prompt}
            if image_values:
                message["images"] = [b for _, b in image_values]
            raw = request(
                profile,
                "api/chat",
                dict(
                    model=profile["model"],
                    messages=[message],
                    stream=False,
                    think=False,
                    options=dict(temperature=0, num_predict=max_tokens),
                ),
                timeout,
            )
            text = raw.get("message", {}).get("content")
            tokens = raw.get("eval_count")
            complete = (
                raw.get("done") is True
                and raw.get("done_reason") not in ("length", "max_tokens")
                and type(tokens) is int
                and tokens < max_tokens
            )
        else:
            content = [{"type": "text", "text": prompt}] + [
                {
                    "type": "image_url",
                    "image_url": {"url": "data:" + mime + ";base64," + b},
                }
                for mime, b in image_values
            ]
            raw = request(
                profile,
                "chat/completions",
                dict(
                    model=profile["model"],
                    messages=[
                        {"role": "user", "content": content if image_values else prompt}
                    ],
                    stream=False,
                    temperature=0,
                    max_tokens=max_tokens,
                ),
                timeout,
            )
            choices = raw.get("choices", [])
            if len(choices) != 1:
                raise ValueError("Expected one local model answer")
            text = choices[0].get("message", {}).get("content")
            tokens = raw.get("usage", {}).get("completion_tokens")
            complete = choices[0].get("finish_reason") == "stop" and (
                type(tokens) is not int or tokens < max_tokens
            )
        if not isinstance(text, str) or not text.strip():
            raise ValueError(
                "Local model returned no textual answer; no tool calls are executed"
            )
        return dict(
            text=text,
            generated_tokens=tokens,
            complete=complete,
            seconds=time.perf_counter() - started,
            model=raw.get("model", profile["model"]),
            raw_response=raw,
        )
