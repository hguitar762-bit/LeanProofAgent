"""Deterministic backend for offline plumbing checks, not model evaluation."""

from __future__ import annotations


class OfflineMockBackend:
    """Return one generic tactic without inspecting benchmark-specific content."""

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        return "by\n  simp"
