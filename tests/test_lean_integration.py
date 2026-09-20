from __future__ import annotations

from pathlib import Path

import pytest

from lean_proof_agent import EvaluationRunner, LeanProblem, LeanVerifier, ProofAgent
from lean_proof_agent.offline_backend import OfflineMockBackend


ROOT = Path(__file__).resolve().parents[1]


class SequenceLLM:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.prompts: list[str] = []

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        self.prompts.append(user_prompt)
        return next(self.responses)


@pytest.mark.lean
def test_verifier_accepts_valid_and_rejects_invalid(tmp_path: Path) -> None:
    verifier = LeanVerifier(ROOT)
    valid = tmp_path / "valid.lean"
    valid.write_text("import Mathlib\nexample : 2 + 2 = 4 := by norm_num\n", encoding="utf-8")
    invalid = tmp_path / "invalid.lean"
    invalid.write_text("import Mathlib\nexample : 2 + 2 = 5 := by norm_num\n", encoding="utf-8")

    assert verifier.verify(valid).success
    rejected = verifier.verify(invalid)
    assert not rejected.success
    assert rejected.exit_code != 0
    assert rejected.compiler_feedback


@pytest.mark.lean
def test_agent_repairs_using_real_lean_feedback(tmp_path: Path) -> None:
    llm = SequenceLLM(["by\n  exact 0", "by\n  omega"])
    agent = ProofAgent(
        llm,
        LeanVerifier(ROOT),
        max_attempts=2,
        artifacts_root=tmp_path / "runs",
    )
    result = agent.solve(
        LeanProblem("repair", "theorem repair (n : ℕ) : n + 0 = n")
    )

    assert result.success
    assert len(result.attempts) == 2
    assert not result.attempts[0].verification.success
    assert result.attempts[1].verification.success
    assert "Lean feedback:" in llm.prompts[1]
    assert result.final_proof == "by\n  omega"
    assert (result.run_dir / "attempt_01.json").is_file()
    assert (result.run_dir / "attempt_02.json").is_file()
    assert (result.run_dir / "summary.json").is_file()


@pytest.mark.lean
def test_evaluation_uses_real_lean_as_success_standard(tmp_path: Path) -> None:
    result = EvaluationRunner(
        OfflineMockBackend(),
        LeanVerifier(ROOT),
        max_attempts=1,
        output_root=tmp_path / "evaluations",
    ).run(
        (
            LeanProblem(
                "evaluation_real_lean",
                "theorem evaluation_real_lean (n : ℕ) : n + 0 = n",
                category="arithmetic",
            ),
        )
    )
    assert result.verified_problems == 1
    assert result.problems[0].verified
    assert (result.evaluation_dir / "evaluation.json").is_file()
