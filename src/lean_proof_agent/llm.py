"""Model-neutral LLM interface and response normalization."""

from __future__ import annotations

from typing import Protocol
import re

from .models import reject_unsafe_lean


class LLMBackend(Protocol):
    """Minimal interface any synchronous text-generation backend can implement."""

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        """Return a candidate Lean proof as text."""


_FENCE_RE = re.compile(r"^```(?:lean)?\s*\n?(.*?)\n?```$", re.DOTALL | re.IGNORECASE)


def normalize_proof(response: str) -> str:
    """Remove a single optional Markdown fence and enforce the safety policy."""

    text = response.strip()
    match = _FENCE_RE.fullmatch(text)
    if match:
        text = match.group(1).strip()
    if text.startswith(":="):
        text = text[2:].strip()
    if not text:
        raise ValueError("LLM returned an empty proof")
    if "```" in text:
        raise ValueError("LLM response contains an unmatched or extra code fence")
    reject_unsafe_lean(text, label="generated proof")
    return text
