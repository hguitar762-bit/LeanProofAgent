from __future__ import annotations

from pathlib import Path

from lean_proof_agent.agent import ProofAgent
from lean_proof_agent.models import LeanProblem, VerificationResult


class RepeatingLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0
        self.prompts: list[str] = []

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        self.prompts.append(user_prompt)
        return self.response


class AlwaysFailVerifier:
    def __init__(self) -> None:
        self.calls = 0

    def verify(self, source_path: Path) -> VerificationResult:
        self.calls += 1
        return VerificationResult(
            success=False,
            command=("lake", "env", "lean", str(source_path)),
            exit_code=1,
            stdout="example.lean:1:1: error: unsolved goals",
            stderr="",
            duration_seconds=0.01,
        )


def test_agent_stops_at_max_attempts_and_returns_feedback(tmp_path: Path) -> None:
    backend = RepeatingLLM("by\n  exact True.intro")
    verifier = AlwaysFailVerifier()
    agent = ProofAgent(
        backend,
        verifier,
        max_attempts=2,
        artifacts_root=tmp_path,
    )
    result = agent.solve(LeanProblem("bounded", "theorem bounded : False"))

    assert not result.success
    assert len(result.attempts) == 2
    assert backend.calls == 2
    assert verifier.calls == 2
    assert "unsolved goals" in backend.prompts[1]


def test_unsafe_proof_is_failed_without_invoking_lean(tmp_path: Path) -> None:
    backend = RepeatingLLM("by\n  sorry")
    verifier = AlwaysFailVerifier()
    result = ProofAgent(
        backend,
        verifier,
        max_attempts=1,
        artifacts_root=tmp_path,
    ).solve(LeanProblem("safe", "theorem safe : True"))

    assert not result.success
    assert verifier.calls == 0
    assert result.attempts[0].verification.command == ()
    assert "forbidden token" in result.attempts[0].verification.compiler_feedback
