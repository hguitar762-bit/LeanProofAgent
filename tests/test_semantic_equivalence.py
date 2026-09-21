from __future__ import annotations

import json
from pathlib import Path

import pytest

from lean_proof_agent.models import VerificationResult
from lean_proof_agent.semantic_equivalence import (
    SemanticEquivalenceChecker,
    load_statement_file,
    merge_imports,
    theorem_to_proposition,
)
from lean_proof_agent.verifier import LeanVerifier


ROOT = Path(__file__).resolve().parents[1]


class GenericAesopBackend:
    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        return "by\n  aesop"


class FailingBackend:
    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        raise RuntimeError("provider unavailable")


class SequenceVerifier:
    def __init__(self, outcomes: list[bool]) -> None:
        self.outcomes = iter(outcomes)
        self.sources: list[str] = []

    def verify(self, source_path: Path) -> VerificationResult:
        self.sources.append(source_path.read_text(encoding="utf-8"))
        success = next(self.outcomes)
        return VerificationResult(
            success=success,
            command=("lake", "env", "lean", str(source_path)),
            exit_code=0 if success else 1,
            stdout="" if success else "error: unsolved goals",
            stderr="",
            duration_seconds=0.01,
        )


@pytest.mark.parametrize(
    ("statement", "proposition"),
    [
        ("theorem p : True", "True"),
        ("theorem p (n : ℕ) : n = n", "∀ (n : ℕ), n = n"),
        (
            "theorem p {α : Type} (P : α → Prop) : ∀ x, P x → P x",
            "∀ {α : Type} (P : α → Prop), ∀ x, P x → P x",
        ),
    ],
)
def test_theorem_to_proposition_closes_explicit_binders(
    statement: str, proposition: str
) -> None:
    assert theorem_to_proposition(statement) == proposition


def test_checker_requires_both_kernel_verified_directions(tmp_path: Path) -> None:
    verifier = SequenceVerifier([True, True])
    result = SemanticEquivalenceChecker(
        GenericAesopBackend(), verifier, max_attempts=1, artifacts_root=tmp_path
    ).check(
        "theorem reference (n : ℕ) : n + 0 = n",
        "theorem generated (m : ℕ) : m + 0 = m",
    )

    assert result.forward.status == "verified"
    assert result.backward.status == "verified"
    assert result.result == "equivalent"
    assert "∀ (n : ℕ)" in result.forward.theorem
    assert "∀ (m : ℕ)" in result.forward.theorem
    assert (result.run_dir / "input.json").is_file()
    summary = json.loads((result.run_dir / "summary.json").read_text("utf-8"))
    assert summary["result"] == "equivalent"
    assert summary["forward"]["proof_attempts"] == 1
    assert summary["backward"]["proof_attempts"] == 1


@pytest.mark.parametrize(
    ("label", "outcomes", "expected"),
    [
        ("same_variable_renamed", [True, True], "equivalent"),
        ("logical_reordering", [True, True], "equivalent"),
        ("quantifier_order", [True, True], "equivalent"),
        ("stronger_statement", [False, True], "unknown"),
        ("weaker_statement", [True, False], "unknown"),
        ("missing_assumption", [False, True], "unknown"),
        ("wrong_domain", [False, True], "unknown"),
    ],
)
def test_case_matrix_never_turns_failed_search_into_inequivalence(
    tmp_path: Path, label: str, outcomes: list[bool], expected: str
) -> None:
    result = SemanticEquivalenceChecker(
        GenericAesopBackend(),
        SequenceVerifier(outcomes),
        max_attempts=1,
        artifacts_root=tmp_path / label,
    ).check(
        f"theorem {label}_reference (P Q : Prop) : P → Q",
        f"theorem {label}_generated (P Q : Prop) : Q → P",
    )
    assert result.result == expected
    assert result.result != "not_equivalent"
    if not all(outcomes):
        assert "unknown" in {result.forward.status, result.backward.status}


def test_statement_file_loader_and_import_merge(tmp_path: Path) -> None:
    reference_path = tmp_path / "reference.json"
    reference_path.write_text(
        json.dumps(
            {
                "reference_statement": "theorem ref : True",
                "imports": ["Mathlib", "Mathlib.Data.Nat.Basic"],
            }
        ),
        encoding="utf-8",
    )
    generated_path = tmp_path / "generated.json"
    generated_path.write_text(
        json.dumps(
            {"final_theorem": "theorem gen : True", "imports": ["Mathlib"]}
        ),
        encoding="utf-8",
    )
    reference = load_statement_file(reference_path)
    generated = load_statement_file(generated_path)
    assert merge_imports(reference.imports, generated.imports) == (
        "Mathlib",
        "Mathlib.Data.Nat.Basic",
    )


def test_operational_failure_is_failed_but_combined_result_remains_unknown(
    tmp_path: Path,
) -> None:
    result = SemanticEquivalenceChecker(
        FailingBackend(),
        SequenceVerifier([]),
        max_attempts=1,
        artifacts_root=tmp_path,
    ).check("theorem ref : True", "theorem gen : True")
    assert result.forward.status == "failed"
    assert result.backward.status == "failed"
    assert result.result == "unknown"
    assert "provider unavailable" in (result.forward.error or "")


@pytest.mark.lean
def test_equivalence_checker_uses_real_lean_for_both_directions(
    tmp_path: Path,
) -> None:
    result = SemanticEquivalenceChecker(
        GenericAesopBackend(),
        LeanVerifier(ROOT),
        max_attempts=1,
        artifacts_root=tmp_path,
    ).check(
        "theorem renamed_reference (n : ℕ) : n + 0 = n",
        "theorem renamed_generated (m : ℕ) : m + 0 = m",
    )
    assert result.result == "equivalent"
    assert result.forward.proof_result is not None
    assert result.backward.proof_result is not None
    assert result.forward.proof_result.attempts[0].verification.command
    assert result.backward.proof_result.attempts[0].verification.command
