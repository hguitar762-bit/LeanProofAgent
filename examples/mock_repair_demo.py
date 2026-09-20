"""Offline demo: a mock model, a real compiler error, and real Lean verification."""

from __future__ import annotations

from pathlib import Path
import tempfile

from lean_proof_agent import LeanProblem, LeanVerifier, ProofAgent


class RepairingMockLLM:
    """Deliberately fail once, then confirm that Lean feedback was returned."""

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        if self.calls == 1:
            return "by\n  exact 0"
        if "Lean feedback:" not in user_prompt or "error:" not in user_prompt:
            raise RuntimeError("repair prompt did not contain the real compiler error")
        return "by\n  omega"


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    problem = LeanProblem(
        "offline_repair_demo",
        "theorem offline_repair_demo (n : ℕ) : n + 0 = n",
        description="Exercise the repair loop without spending API credits.",
    )
    with tempfile.TemporaryDirectory(prefix="leanproof-demo-") as directory:
        agent = ProofAgent(
            RepairingMockLLM(),
            LeanVerifier(project_root),
            max_attempts=2,
            artifacts_root=Path(directory),
        )
        result = agent.solve(problem)
        if not result.success or len(result.attempts) != 2:
            raise SystemExit("demo failed")
        print("Demo succeeded: attempt 1 failed in Lean; attempt 2 was verified by Lean.")
        print(f"Lean error excerpt: {result.attempts[0].verification.compiler_feedback.splitlines()[0]}")
        print(f"Verified proof: {result.final_proof}")


if __name__ == "__main__":
    main()
