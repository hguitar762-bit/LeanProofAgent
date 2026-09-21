"""Offline v0.5 evaluation demo using a fixed fixture and real Lean."""

from __future__ import annotations

from pathlib import Path
import tempfile

from lean_proof_agent.formalization_benchmarks import FormalizationBenchmark
from lean_proof_agent.formalization_evaluation import FormalizationEvaluationRunner
from lean_proof_agent.verifier import LeanVerifier


class DemoBackend:
    """Sequence fixture: invalid statement, repaired statement, then proof."""

    def __init__(self) -> None:
        self._responses = iter(
            [
                "theorem offline_eval_demo (n : ℕ) : n + missing_symbol = n",
                "theorem offline_eval_demo (n : ℕ) : n + 0 = n",
                "by\n  simp",
            ]
        )

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        return next(self._responses)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    benchmark = FormalizationBenchmark(
        id="offline_eval_demo",
        natural_language="For every natural number n, n plus zero equals n.",
        reference_statement="theorem offline_eval_demo (n : ℕ) : n + 0 = n",
        imports=("Mathlib",),
        category="arithmetic",
        assumptions=("n is a natural number",),
        ambiguity_notes="The domain and quantifier are explicit.",
    )
    verifier = LeanVerifier(root)
    with tempfile.TemporaryDirectory(prefix="lean-proof-formalization-demo-") as temp:
        result = FormalizationEvaluationRunner(
            DemoBackend(),
            verifier,
            verifier,
            max_formalization_attempts=2,
            max_proof_attempts=1,
            output_root=Path(temp),
            backend_name="offline-sequence-fixture",
        ).run((benchmark,))
        item = result.problems[0]
        print("Offline autoformalization evaluation demo")
        print(f"well_formed={item.well_formed}")
        print(f"repair_succeeded={item.repair_succeeded}")
        print(f"proof_verified={item.proof_verified}")
        print(f"comparison={item.comparison}")
        print(f"semantic_review={item.semantic_review}")
        print(f"statement_success_rate={result.statement_success_rate:.0%}")
        print(
            "end_to_end_proof_verification_rate="
            f"{result.end_to_end_proof_verification_rate:.0%}"
        )


if __name__ == "__main__":
    main()
