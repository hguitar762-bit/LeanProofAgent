"""Backend selection shared by the CLI and experiment runner."""

from __future__ import annotations

import os

from .llm import LLMBackend
from .ollama_backend import OllamaBackend
from .openai_backend import OpenAIBackend


def resolve_model(backend: str, requested: str | None) -> str:
    if requested and requested.strip():
        return requested
    if backend == "ollama":
        model = os.environ.get("OLLAMA_MODEL")
        if not model:
            raise ValueError("provide --model or set OLLAMA_MODEL for the Ollama backend")
        return model
    if backend == "openai":
        return os.environ.get("OPENAI_MODEL", "gpt-5.5")
    raise ValueError(f"unsupported model backend: {backend}")


def create_backend(
    backend: str,
    model: str | None,
    *,
    check_available: bool = True,
) -> tuple[LLMBackend, str]:
    resolved = resolve_model(backend, model)
    if backend == "openai":
        return OpenAIBackend(resolved), resolved
    if backend == "ollama":
        local = OllamaBackend(resolved)
        if check_available:
            local.check_available()
        return local, resolved
    raise ValueError(f"unsupported model backend: {backend}")
