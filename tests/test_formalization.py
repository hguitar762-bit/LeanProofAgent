from __future__ import annotations

import json
from pathlib import Path

import pytest

from lean_proof_agent.formalization import (
    AutoformalizationAgent,
    NaturalLanguageProblem,
    normalize_theorem_statement,
)
from lean_proof_agent.models import VerificationResult
from lean_proof_agent.text_benchmarks import list_text_benchmarks
from lean_proof_agent.verifier import LeanVerifier


ROOT = Path(__file__).resolve().parents[1]


class SequenceBackend:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.prompts: list[str] = []
        self.system_prompts: list[str] = []

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        self.system_prompts.append(system_prompt)
        self.prompts.append(user_prompt)
        return next(self.responses)


class MockLeanVerifier:
    def __init__(self) -> None:
        self.sources: list[str] = []

    def verify(self, source_path: Path) -> VerificationResult:
        source = source_path.read_text(encoding="utf-8")
        self.sources.append(source)
        success = "missing_symbol" not in source
        return VerificationResult(
            success=success,
            command=("lake", "env", "lean", str(source_path)),
            exit_code=0 if success else 1,
            stdout="" if success else "error: unknown identifier 'missing_symbol'",
            stderr="",
            duration_seconds=0.01,
        )


def test_autoformalization_repairs_statement_then_reuses_proof_agent(
    tmp_path: Path,
) -> None:
    backend = SequenceBackend(
        [
            "theorem auto_test (n : ℕ) : n + missing_symbol = n",
            "theorem auto_test (n : ℕ) : n + 0 = n",
            "by\n  rfl",
        ]
    )
    verifier = MockLeanVerifier()
    result = AutoformalizationAgent(
        backend,
        verifier,
        verifier,
        max_formalization_attempts=2,
        max_proof_attempts=1,
        artifacts_root=tmp_path,
    ).solve(
        NaturalLanguageProblem(
            "auto_test",
            "For every natural number n, n plus zero equals n.",
            category="arithmetic",
        )
    )

    assert result.success
    assert result.final_theorem == "theorem auto_test (n : ℕ) : n + 0 = n"
    assert result.verified_proof == "by\n  rfl"
    assert len(result.formalization_attempts) == 2
    assert result.proof_result is not None
    assert len(result.proof_result.attempts) == 1
    assert "Lean feedback:" in backend.prompts[1]
    assert "missing_symbol" in backend.prompts[1]
    assert "axiom auto_test" in verifier.sources[0]
    assert "axiom auto_test" in verifier.sources[1]
    assert "theorem auto_test" in verifier.sources[2]

    assert (result.run_dir / "input.json").is_file()
    assert (result.run_dir / "formalization_01.json").is_file()
    assert (result.run_dir / "formalization_02.json").is_file()
    assert (result.run_dir / "summary.json").is_file()
    saved_input = json.loads(
        (result.run_dir / "input.json").read_text(encoding="utf-8")
    )
    first = json.loads(
        (result.run_dir / "formalization_01.json").read_text(encoding="utf-8")
    )
    second = json.loads(
        (result.run_dir / "formalization_02.json").read_text(encoding="utf-8")
    )
    summary = json.loads(
        (result.run_dir / "summary.json").read_text(encoding="utf-8")
    )
    assert saved_input["natural_language"].startswith("For every natural number")
    assert "missing_symbol" in first["lean_feedback"]
    assert second["lean_feedback"] is None
    assert summary["success"] is True
    assert summary["verified_proof"] == "by\n  rfl"
    assert (result.proof_result.run_dir / "attempt_01.json").is_file()


@pytest.mark.parametrize(
    "response",
    [
        "theorem unsafe : True := by trivial",
        "theorem unsafe : sorry",
        "theorem unsafe : admit",
        "axiom unsafe : True",
    ],
)
def test_unsafe_formalizations_are_rejected_before_lean(
    tmp_path: Path, response: str
) -> None:
    backend = SequenceBackend([response])
    verifier = MockLeanVerifier()
    result = AutoformalizationAgent(
        backend,
        verifier,
        verifier,
        max_formalization_attempts=1,
        artifacts_root=tmp_path,
    ).solve(NaturalLanguageProblem("unsafe", "A proposition."))

    assert not result.success
    assert result.final_problem is None
    assert verifier.sources == []
    assert result.formalization_attempts[0].verification.command == ()


def test_statement_normalization_accepts_one_fence_but_no_proof_body() -> None:
    assert normalize_theorem_statement("```lean\ntheorem p : True\n```") == (
        "theorem p : True"
    )
    with pytest.raises(ValueError, match="proof body"):
        normalize_theorem_statement("theorem p : True := by trivial")
    with pytest.raises(ValueError, match="extra Lean commands"):
        normalize_theorem_statement("theorem p : True\n#check Nat")
    with pytest.raises(ValueError, match="must be named"):
        normalize_theorem_statement("theorem other : True", expected_name="p")


def test_bundled_text_benchmarks_cover_requested_categories() -> None:
    problems = list_text_benchmarks()
    assert len(problems) == 3
    assert {problem.category for problem in problems} == {
        "arithmetic",
        "logic",
        "algebra",
    }


@pytest.mark.lean
def test_autoformalization_uses_real_lean_feedback_and_verification(
    tmp_path: Path,
) -> None:
    backend = SequenceBackend(
        [
            "theorem autoformalization_real : ℕ",
            "theorem autoformalization_real (n : ℕ) : n + 0 = n",
            "by\n  omega",
        ]
    )
    verifier = LeanVerifier(ROOT)
    result = AutoformalizationAgent(
        backend,
        verifier,
        verifier,
        max_formalization_attempts=2,
        max_proof_attempts=1,
        artifacts_root=tmp_path,
    ).solve(
        NaturalLanguageProblem(
            "autoformalization_real",
            "For every natural number n, n + 0 = n.",
        )
    )

    assert result.success
    assert len(result.formalization_attempts) == 2
    assert not result.formalization_attempts[0].verification.success
    assert result.formalization_attempts[1].verification.success
    assert "Lean feedback:" in backend.prompts[1]
    assert "not a proposition" in backend.prompts[1]
    assert result.verified_proof == "by\n  omega"
