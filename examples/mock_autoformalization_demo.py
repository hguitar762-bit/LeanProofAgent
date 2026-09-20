"""Offline natural-language formalization and proof demo using real Lean."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile

from lean_proof_agent import (
    AutoformalizationAgent,
    LeanVerifier,
    NaturalLanguageProblem,
)


class RepairingAutoformalizationMock:
    """Emit one invalid statement, repair it from Lean feedback, then prove it."""

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        if self.calls == 1:
            return "theorem offline_auto_demo : ℕ"
        if self.calls == 2:
            if (
                "Lean feedback:" not in user_prompt
                or "not a proposition" not in user_prompt
            ):
                raise RuntimeError("formalization repair prompt lacks Lean feedback")
            return "theorem offline_auto_demo (n : ℕ) : n + 0 = n"
        if "<YOUR_PROOF>" not in user_prompt:
            raise RuntimeError("valid theorem was not passed to ProofAgent")
        return "by\n  omega"


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    project_root = Path(__file__).resolve().parents[1]
    problem = NaturalLanguageProblem(
        "offline_auto_demo",
        "For every natural number n, n plus zero equals n.",
        category="arithmetic",
    )
    with tempfile.TemporaryDirectory(prefix="leanproof-auto-demo-") as directory:
        verifier = LeanVerifier(project_root)
        result = AutoformalizationAgent(
            RepairingAutoformalizationMock(),
            verifier,
            verifier,
            max_formalization_attempts=2,
            max_proof_attempts=1,
            artifacts_root=Path(directory),
        ).solve(problem)
        if not result.success or len(result.formalization_attempts) != 2:
            raise SystemExit("autoformalization demo failed")
        first_error = result.formalization_attempts[0].verification.compiler_feedback
        print("Autoformalization demo succeeded with real Lean checks.")
        print(f"Natural language: {problem.text}")
        print(f"First Lean error: {first_error.splitlines()[0]}")
        print(f"Repaired theorem: {result.final_theorem}")
        print(f"Verified proof: {result.verified_proof}")


if __name__ == "__main__":
    main()
