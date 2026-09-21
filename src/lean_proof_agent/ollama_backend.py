"""Local Ollama HTTP backend using only the Python standard library."""

from __future__ import annotations

import json
import os
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import GenerationResult, TokenUsage


class OllamaBackend:
    """Generate text through Ollama's local, non-streaming HTTP API."""

    def __init__(
        self,
        model: str,
        *,
        base_url: str | None = None,
        timeout_seconds: float = 600.0,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("Ollama model must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("Ollama timeout must be positive")
        host = (base_url or os.environ.get("OLLAMA_HOST") or "http://localhost:11434")
        if "://" not in host:
            host = f"http://{host}"
        self.model = model
        self.base_url = host.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._opener = opener or urlopen

    def check_available(self) -> None:
        """Fail clearly when the Ollama service or requested model is unavailable."""

        payload = self._request_json(Request(f"{self.base_url}/api/tags", method="GET"))
        models = payload.get("models")
        if not isinstance(models, list):
            raise RuntimeError("Ollama /api/tags response did not contain a models list")
        names = {
            value
            for item in models
            if isinstance(item, dict)
            for value in (item.get("name"), item.get("model"))
            if isinstance(value, str)
        }
        accepted = {self.model}
        if ":" not in self.model:
            accepted.add(f"{self.model}:latest")
        if names.isdisjoint(accepted):
            installed = ", ".join(sorted(names)) or "none"
            raise RuntimeError(
                f"Ollama model {self.model!r} is not installed. "
                f"Run `ollama pull {self.model}`. Installed models: {installed}"
            )

    def generate(self, *, system_prompt: str, user_prompt: str) -> GenerationResult:
        body = json.dumps(
            {
                "model": self.model,
                "system": system_prompt,
                "prompt": user_prompt,
                "stream": False,
            }
        ).encode("utf-8")
        request = Request(
            f"{self.base_url}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        payload = self._request_json(request)
        text = payload.get("response")
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Ollama response did not contain generated text")
        return GenerationResult(text=text, token_usage=_read_token_usage(payload))

    def _request_json(self, request: Request) -> dict[str, Any]:
        try:
            with self._opener(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            detail = _error_detail(exc.read())
            if exc.code == 404:
                raise RuntimeError(
                    f"Ollama model or endpoint was not found at {self.base_url}: "
                    f"{detail}. Run `ollama pull {self.model}` if the service is running."
                ) from exc
            raise RuntimeError(
                f"Ollama request failed with HTTP {exc.code}: {detail}"
            ) from exc
        except (URLError, ConnectionError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise RuntimeError(
                f"Could not connect to Ollama at {self.base_url}: {reason}. "
                "Start Ollama (for example, `ollama serve`) and retry."
            ) from exc
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Ollama returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Ollama returned a non-object JSON response")
        error = payload.get("error")
        if isinstance(error, str) and error:
            raise RuntimeError(f"Ollama generation failed: {error}")
        return payload


def _read_token_usage(payload: dict[str, Any]) -> TokenUsage | None:
    input_tokens = payload.get("prompt_eval_count")
    output_tokens = payload.get("eval_count")
    if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
        return None
    if input_tokens < 0 or output_tokens < 0:
        return None
    return TokenUsage(input_tokens, output_tokens, input_tokens + output_tokens)


def _error_detail(raw: bytes) -> str:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return raw.decode("utf-8", errors="replace").strip() or "no error detail"
    if isinstance(payload, dict) and isinstance(payload.get("error"), str):
        return payload["error"]
    return "no error detail"
