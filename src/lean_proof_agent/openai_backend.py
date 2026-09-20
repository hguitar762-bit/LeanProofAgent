"""OpenAI Responses API backend."""

from __future__ import annotations

import os
from typing import Any


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

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        response = self._client.responses.create(
            model=self.model,
            instructions=system_prompt,
            input=user_prompt,
        )
        text = response.output_text
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("OpenAI response did not contain output text")
        return text
