from __future__ import annotations

import pytest

from lean_proof_agent.llm import normalize_proof
from lean_proof_agent.models import LeanProblem, UnsafeLeanCodeError


def test_problem_renders_exact_source() -> None:
    problem = LeanProblem("identity", "theorem identity (n : ℕ) : n = n")
    assert problem.source_with("by\n  rfl") == (
        "import Mathlib\n\ntheorem identity (n : ℕ) : n = n := by\n  rfl\n"
    )


@pytest.mark.parametrize("token", ["sorry", "admit", "axiom"])
def test_forbidden_escape_hatches_are_rejected(token: str) -> None:
    with pytest.raises(UnsafeLeanCodeError):
        normalize_proof(f"by\n  {token}")


def test_normalize_accepts_one_optional_fence() -> None:
    assert normalize_proof("```lean\nby\n  rfl\n```") == "by\n  rfl"


def test_theorem_must_not_include_answer() -> None:
    with pytest.raises(ValueError, match="proof body"):
        LeanProblem("cheat", "theorem cheat : True := by trivial")
