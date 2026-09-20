"""OpenAI Responses API backend."""

from __future__ import annotations

import os
from typing import Any

from .models import GenerationResult, TokenUsage


class OpenAIBackend:
    """Generate proof text with the official OpenAI Python SDK.

    The constructor intentionally has no API-key parameter. The SDK reads
    ``OPENAI_API_KEY`` from the process environment.
    """

    def __init__(self, model: str, *, client: Any | None = None) -> None:
        if not model.strip():
            raise ValueError("model must not be empty")
        self.model = model
        if client is None:
            if not os.environ.get("OPENAI_API_KEY"):
                raise RuntimeError("OPENAI_API_KEY is not set in the environment")
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError(
                    "OpenAI backend requires: pip install 'lean-proof-agent[openai]'"
                ) from exc
            client = OpenAI()
        self._client = client

    def generate(self, *, system_prompt: str, user_prompt: str) -> GenerationResult:
        response = self._client.responses.create(
            model=self.model,
            instructions=system_prompt,
            input=user_prompt,
        )
        text = response.output_text
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("OpenAI response did not contain output text")
        return GenerationResult(text=text, token_usage=_read_token_usage(response))


def _read_token_usage(response: Any) -> TokenUsage | None:
    """Read the optional usage object without inventing missing values."""

    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)
    if not (
        isinstance(input_tokens, int)
        and isinstance(output_tokens, int)
        and isinstance(total_tokens, int)
    ):
        return None
    if min(input_tokens, output_tokens, total_tokens) < 0:
        return None
    return TokenUsage(input_tokens, output_tokens, total_tokens)
