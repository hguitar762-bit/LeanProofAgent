"""Prompt construction for first-pass generation and compiler-guided repair."""

from __future__ import annotations

from .models import LeanProblem


SYSTEM_PROMPT = """You write Lean 4 proofs checked against Mathlib.
Return only the proof term, normally beginning with `by`; do not repeat the theorem.
Never use `sorry`, `admit`, `axiom`, or any construct intended to bypass the kernel.
Do not use Markdown fences or prose. Prefer short, robust Mathlib tactics."""


def build_user_prompt(
    problem: LeanProblem,
    *,
    attempt_number: int,
    previous_proof: str | None = None,
    compiler_error: str | None = None,
    max_feedback_chars: int = 12_000,
) -> str:
    """Build a prompt that makes compiler feedback the repair signal."""

    imports = "\n".join(f"import {item}" for item in problem.imports)
    base = (
        f"Attempt {attempt_number}. Complete this Lean file:\n\n"
        f"{imports}\n\n{problem.theorem.strip()} := <YOUR_PROOF>"
    )
    if previous_proof is None or compiler_error is None:
        return base
    feedback = compiler_error[-max_feedback_chars:]
    return (
        f"{base}\n\n"
        "The previous proof failed. Repair it using the exact Lean feedback below.\n\n"
        f"Previous proof:\n{previous_proof}\n\n"
        f"Lean feedback:\n{feedback}"
    )
