"""Offline semantic-equivalence cases using one generic tactic and real Lean."""

from __future__ import annotations

import argparse
from pathlib import Path
import tempfile

from lean_proof_agent.semantic_equivalence import SemanticEquivalenceChecker
from lean_proof_agent.verifier import LeanVerifier


class GenericAesopBackend:
    """A benchmark-agnostic offline proof-search fixture."""

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        return "by\n  aesop"


CASES = (
    (
        "renamed_binder",
        "theorem renamed_reference (n : ℕ) : n + 0 = n",
        "theorem renamed_generated (m : ℕ) : m + 0 = m",
    ),
    (
        "logical_reordering",
        "theorem logic_reference (P Q : Prop) : (P ∧ Q) ↔ (Q ∧ P)",
        "theorem logic_generated (A B : Prop) : (B ∧ A) ↔ (A ∧ B)",
    ),
    (
        "quantifier_order",
        "theorem quantifier_reference {α β : Type} (R : α → β → Prop) : ∀ x : α, ∀ y : β, R x y",
        "theorem quantifier_generated {α β : Type} (R : α → β → Prop) : ∀ y : β, ∀ x : α, R x y",
    ),
    (
        "stronger_statement",
        "theorem weaker_reference : ∃ n : ℕ, n = 0",
        "theorem stronger_generated : ∃ n : ℕ, n = 0 ∧ n = 1",
    ),
    (
        "weaker_statement",
        "theorem stronger_reference : ∃ n : ℕ, n = 0 ∧ n = 1",
        "theorem weaker_generated : ∃ n : ℕ, n = 0",
    ),
    (
        "missing_assumption",
        "theorem assumption_reference (x : ℝ) (hx : x ≠ 0) : x * x⁻¹ = 1",
        "theorem assumption_generated (x : ℝ) : x * x⁻¹ = 1",
    ),
    (
        "wrong_domain",
        "theorem natural_domain_reference (n : ℕ) : 0 ≤ n",
        "theorem integer_domain_generated (z : ℤ) : 0 ≤ z",
    ),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cases", nargs="*", help="optional case labels")
    selected = set(parser.parse_args().cases)
    unknown = selected - {label for label, _, _ in CASES}
    if unknown:
        raise ValueError(f"unknown case(s): {', '.join(sorted(unknown))}")
    root = Path(__file__).resolve().parents[1]
    verifier = LeanVerifier(root)
    with tempfile.TemporaryDirectory(prefix="lean-proof-equivalence-demo-") as temp:
        for label, reference, generated in CASES:
            if selected and label not in selected:
                continue
            result = SemanticEquivalenceChecker(
                GenericAesopBackend(),
                verifier,
                max_attempts=1,
                artifacts_root=Path(temp) / label,
            ).check(reference, generated)
            print(
                f"{label}: forward={result.forward.status}, "
                f"backward={result.backward.status}, result={result.result}"
            )


if __name__ == "__main__":
    main()
