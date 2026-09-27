from __future__ import annotations

import json
from pathlib import Path

import pytest

from lean_proof_agent.agent import ProofAgent
from lean_proof_agent.models import LeanProblem, VerificationResult
from lean_proof_agent.premise_retrieval import MathlibRetriever
from lean_proof_agent.premise_retrieval import _query_tokens, _search_tokens
from lean_proof_agent.verifier import LeanVerifier


class CapturingBackend:
    def __init__(self, response: str = "by simp") -> None:
        self.response = response
        self.prompts: list[str] = []

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        self.prompts.append(user_prompt)
        return self.response


class SuccessVerifier:
    def verify(self, source_path: Path) -> VerificationResult:
        return VerificationResult(True, (), 0, "", "", 0.0)


@pytest.mark.lean
def test_mathlib_retrieval_is_repeatable_and_declarations_exist(
    tmp_path: Path,
) -> None:
    retriever = MathlibRetriever(project_root=Path.cwd())
    problem = LeanProblem(
        "sample",
        "theorem sample {α β : Type} (f : α → β) : Function.Injective f → Function.Injective f",
    )

    first = retriever.retrieve(problem, top_k=10)
    second = retriever.retrieve(problem, top_k=10)

    assert first == second
    assert 1 <= len(first) <= 10
    assert all(item.name and item.signature and item.module for item in first)

    checks = "\n".join(f"#check {item.name}" for item in first)
    source = tmp_path / "retrieved_declarations_exist.lean"
    source.write_text(f"import Mathlib\n\n{checks}\n", encoding="utf-8")
    result = LeanVerifier(Path.cwd(), timeout_seconds=120).verify(source)
    assert result.success, result.compiler_feedback


def test_retriever_contains_no_benchmark_specific_answers() -> None:
    source = (
        Path(__file__).parents[1]
        / "src"
        / "lean_proof_agent"
        / "premise_retrieval.py"
    ).read_text(encoding="utf-8")
    forbidden = {
        "arith_add_zero",
        "algebra_mul_inv_cancel",
        "logic_contraposition",
        "ineq_square_nonnegative",
        "sets_preimage_inter",
        "func_left_inverse_injective",
    }
    assert not any(problem_id in source for problem_id in forbidden)


def test_search_uses_distinctive_name_compounds_not_high_frequency_types() -> None:
    theorem = "theorem any_name_add_zero (n : Nat) : n + 0 = n"
    search = _search_tokens(theorem, _query_tokens(theorem))

    assert "add_zero" in search
    assert "nat" not in search


def test_retrieval_mode_adds_prompt_context_and_persists_candidates(
    tmp_path: Path,
) -> None:
    class FixedRetriever:
        def retrieve(self, problem: LeanProblem, *, top_k: int):
            from lean_proof_agent.premise_retrieval import Premise

            assert top_k == 2
            return (
                Premise("Nat.add_zero", "(n : Nat) : n + 0 = n", "Init.Prelude", 9.0),
                Premise("add_comm", "a + b = b + a", "Mathlib.Algebra.Group.Basic", 4.0),
            )

    backend = CapturingBackend()
    result = ProofAgent(
        backend,
        SuccessVerifier(),
        max_attempts=1,
        artifacts_root=tmp_path,
        premise_retriever=FixedRetriever(),
        premise_top_k=2,
    ).solve(LeanProblem("retrieved", "theorem retrieved (n : Nat) : n + 0 = n"))

    assert "Nat.add_zero" in backend.prompts[0]
    payload = json.loads((result.run_dir / "premises.json").read_text("utf-8"))
    assert payload[0]["name"] == "Nat.add_zero"
    assert payload[0]["module"] == "Init.Prelude"


def test_retrieval_disabled_preserves_baseline_prompt_and_artifacts(
    tmp_path: Path,
) -> None:
    backend = CapturingBackend()
    problem = LeanProblem("baseline", "theorem baseline : True")
    result = ProofAgent(
        backend,
        SuccessVerifier(),
        max_attempts=1,
        artifacts_root=tmp_path,
    ).solve(problem)

    assert backend.prompts == [
        "Attempt 1. Complete this Lean file:\n\n"
        "import Mathlib\n\n"
        "theorem baseline : True := <YOUR_PROOF>"
    ]
    assert not (result.run_dir / "premises.json").exists()
