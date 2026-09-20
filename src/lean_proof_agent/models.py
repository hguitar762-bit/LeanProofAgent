"""Typed domain models used by the proof loop."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


_IMPORT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_FORBIDDEN_RE = re.compile(r"\b(?:sorry|admit|axiom)\b", re.IGNORECASE)
_THEOREM_RE = re.compile(r"^\s*(?:theorem|example)\b", re.DOTALL)


class UnsafeLeanCodeError(ValueError):
    """Raised when generated code tries to bypass proof verification."""


def reject_unsafe_lean(text: str, *, label: str) -> None:
    """Reject explicit proof holes and user-defined axioms."""

    match = _FORBIDDEN_RE.search(text)
    if match:
        raise UnsafeLeanCodeError(
            f"{label} contains forbidden token {match.group(0)!r}"
        )


@dataclass(frozen=True, slots=True)
class LeanProblem:
    """A theorem declaration without a proof body."""

    name: str
    theorem: str
    imports: tuple[str, ...] = ("Mathlib",)
    description: str = ""
    category: str = "uncategorized"

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("problem name must not be empty")
        if not self.category.strip():
            raise ValueError("problem category must not be empty")
        theorem = self.theorem.strip()
        if not _THEOREM_RE.match(theorem):
            raise ValueError("theorem must start with 'theorem' or 'example'")
        if ":=" in theorem:
            raise ValueError("theorem declaration must not contain a proof body")
        reject_unsafe_lean(theorem, label="theorem")
        if not self.imports:
            raise ValueError("at least one Lean import is required")
        invalid = [item for item in self.imports if not _IMPORT_RE.fullmatch(item)]
        if invalid:
            raise ValueError(f"invalid Lean import(s): {', '.join(invalid)}")

    def source_with(self, proof: str) -> str:
        """Render the exact Lean source that will be checked."""

        clean_proof = proof.strip()
        if not clean_proof:
            raise ValueError("proof must not be empty")
        reject_unsafe_lean(clean_proof, label="proof")
        imports = "\n".join(f"import {item}" for item in self.imports)
        return f"{imports}\n\n{self.theorem.strip()} := {clean_proof}\n"


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Result of one real Lean compiler invocation."""

    success: bool
    command: tuple[str, ...]
    exit_code: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False

    @property
    def compiler_feedback(self) -> str:
        parts = [part.strip() for part in (self.stdout, self.stderr) if part.strip()]
        if parts:
            return "\n".join(parts)
        if self.timed_out:
            return "Lean verification timed out."
        return "Lean rejected the proof without compiler output."


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Token counts reported by an LLM provider, when available."""

    input_tokens: int
    output_tokens: int
    total_tokens: int

    def __post_init__(self) -> None:
        if min(self.input_tokens, self.output_tokens, self.total_tokens) < 0:
            raise ValueError("token counts must be non-negative")

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """Generated proof text with optional provider-reported usage."""

    text: str
    token_usage: TokenUsage | None = None


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    """Persisted information for one generation/verification attempt."""

    number: int
    proof: str
    source_path: Path
    verification: VerificationResult
    generation_seconds: float = 0.0
    token_usage: TokenUsage | None = None


@dataclass(frozen=True, slots=True)
class RunResult:
    """Final result of a bounded proof search."""

    problem: LeanProblem
    success: bool
    attempts: tuple[AttemptRecord, ...]
    run_dir: Path

    @property
    def final_proof(self) -> str | None:
        if not self.success or not self.attempts:
            return None
        return self.attempts[-1].proof

    @property
    def token_usage(self) -> TokenUsage | None:
        usages = [item.token_usage for item in self.attempts if item.token_usage]
        if not usages:
            return None
        total = TokenUsage(0, 0, 0)
        for usage in usages:
            total += usage
        return total
