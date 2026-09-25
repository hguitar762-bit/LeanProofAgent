from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

from lean_proof_agent.formalization_benchmarks import load_formalization_benchmarks
from lean_proof_agent.formalization_evaluation import (
    FormalizationEvaluationRunner,
    SemanticReview,
    compare_statements,
    load_semantic_reviews,
    render_formalization_markdown,
)
from lean_proof_agent.experiment_reporting import write_experiment_bundle
from lean_proof_agent.models import GenerationResult, TokenUsage, VerificationResult
from lean_proof_agent.verifier import LeanVerifier


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_DIR = ROOT / "benchmarks" / "formalization"


class SequenceBackend:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        return next(self.responses)


class UsageSequenceBackend(SequenceBackend):
    def generate(self, *, system_prompt: str, user_prompt: str) -> GenerationResult:
        return GenerationResult(
            super().generate(system_prompt=system_prompt, user_prompt=user_prompt),
            TokenUsage(1, 2, 3),
        )


class TimeoutAfterResponsesBackend(UsageSequenceBackend):
    def generate(self, *, system_prompt: str, user_prompt: str) -> GenerationResult:
        try:
            return super().generate(
                system_prompt=system_prompt, user_prompt=user_prompt
            )
        except StopIteration:
            raise TimeoutError("fixture provider timeout") from None


class FixtureVerifier:
    def verify(self, source_path: Path) -> VerificationResult:
        source = source_path.read_text(encoding="utf-8")
        success = "missing_symbol" not in source
        return VerificationResult(
            success=success,
            command=("lake", "env", "lean", str(source_path)),
            exit_code=0 if success else 1,
            stdout="" if success else "error: unknown identifier 'missing_symbol'",
            stderr="",
            duration_seconds=0.01,
        )


def test_curated_benchmark_has_36_reviewed_pairs_across_six_categories() -> None:
    problems = load_formalization_benchmarks(BENCHMARK_DIR)
    assert len(problems) == 36
    counts = {category: 0 for category in {
        "arithmetic", "algebra", "logic", "inequalities", "sets", "functions"
    }}
    for problem in problems:
        counts[problem.category] += 1
        assert problem.imports
        assert problem.assumptions
        assert problem.ambiguity_notes
        assert problem.reference_statement.startswith(f"theorem {problem.id}")
    assert counts == {category: 6 for category in counts}


def test_evaluation_separates_well_formed_proof_and_human_semantics(
    tmp_path: Path,
) -> None:
    benchmark = load_formalization_benchmarks(BENCHMARK_DIR)[0]
    backend = UsageSequenceBackend(
        [
            f"theorem {benchmark.id} (n : ℕ) : n + missing_symbol = n",
            benchmark.reference_statement,
            "by\n  simp",
            "by\n  simp",
            "by\n  simp",
        ]
    )
    verifier = FixtureVerifier()
    result = FormalizationEvaluationRunner(
        backend,
        verifier,
        verifier,
        max_formalization_attempts=2,
        max_proof_attempts=1,
        output_root=tmp_path,
        backend_name="fixture",
    ).run((benchmark,))

    item = result.problems[0]
    assert item.well_formed is True
    assert item.provable is True
    assert item.proof_verified is True
    assert item.comparison == "exact_match"
    assert item.equivalence_forward == "verified"
    assert item.equivalence_backward == "verified"
    assert item.equivalence_result == "equivalent"
    assert item.semantic_review == "unreviewed"
    assert item.semantic_correct is None
    assert item.repair_attempted is True
    assert item.repair_succeeded is True
    assert result.statement_success_rate == 1
    assert result.first_formalization_success_rate == 0
    assert result.formalization_repair_gain_count == 1
    assert result.formalization_repair_gain_percentage_points == 100
    assert result.repair_success_rate == 1
    assert result.average_formalization_attempts == 2
    assert result.end_to_end_proof_verification_rate == 1
    assert result.first_proof_success_rate == 1
    assert result.proof_repair_gain_count == 0
    assert result.average_proof_attempts == 1
    assert result.equivalent_problems == 1
    assert result.semantic_equivalence_rate == 1
    assert result.semantic_unknown_rate == 0
    assert result.token_usage == TokenUsage(5, 10, 15)
    assert result.token_usage_reported_attempts == 5
    assert "human review only" in render_formalization_markdown(result)
    assert (result.evaluation_dir / "evaluation.json").is_file()
    assert (result.evaluation_dir / "summary.md").is_file()
    review_path = result.evaluation_dir / "semantic_reviews.json"
    assert review_path.is_file()
    assert load_semantic_reviews(review_path)[benchmark.id].semantic_review == "unreviewed"

    experiment_dir = tmp_path / "experiment"
    experiment_dir.mkdir()
    write_experiment_bundle(
        result,
        experiment_dir,
        {
            "timestamp_utc": "2026-09-21T00:00:00+00:00",
            "git_commit": "abc123",
            "backend": "fixture",
            "model": "fixture-model",
        },
    )
    assert (experiment_dir / "config.json").is_file()
    assert (experiment_dir / "results.json").is_file()
    assert "Formalization repair gain: +1" in (
        experiment_dir / "summary.md"
    ).read_text("utf-8")
    assert (experiment_dir / "failures.md").is_file()


def test_evaluation_measures_proof_repair_gain(tmp_path: Path) -> None:
    benchmark = load_formalization_benchmarks(BENCHMARK_DIR)[0]
    backend = SequenceBackend(
        [
            benchmark.reference_statement,
            "by\n  exact missing_symbol",
            "by\n  simp",
            "by\n  simp",
            "by\n  simp",
        ]
    )
    verifier = FixtureVerifier()
    result = FormalizationEvaluationRunner(
        backend,
        verifier,
        verifier,
        max_formalization_attempts=1,
        max_proof_attempts=2,
        max_equivalence_attempts=1,
        output_root=tmp_path,
    ).run((benchmark,))

    item = result.problems[0]
    assert item.first_proof_verified is False
    assert item.proof_repair_attempted is True
    assert item.proof_repair_succeeded is True
    assert item.proof_attempts == 2
    assert result.first_proof_success_rate == 0
    assert result.end_to_end_proof_verification_rate == 1
    assert result.proof_repair_gain_count == 1
    assert result.proof_repair_gain_percentage_points == 100


def test_backend_failure_preserves_completed_attempt_metrics(tmp_path: Path) -> None:
    benchmark = load_formalization_benchmarks(BENCHMARK_DIR)[0]
    backend = TimeoutAfterResponsesBackend(
        [benchmark.reference_statement, "by\n  exact missing_symbol"]
    )
    verifier = FixtureVerifier()
    result = FormalizationEvaluationRunner(
        backend,
        verifier,
        verifier,
        max_formalization_attempts=1,
        max_proof_attempts=2,
        max_equivalence_attempts=1,
        output_root=tmp_path,
    ).run((benchmark,))

    item = result.problems[0]
    assert item.first_formalization_well_formed is True
    assert item.well_formed is True
    assert item.generated_statement == benchmark.reference_statement
    assert item.formalization_attempts == 1
    assert item.proof_attempts == 1
    assert item.token_usage == TokenUsage(2, 4, 6)
    assert item.token_usage_reported_attempts == 2
    assert item.run_dir is not None
    assert "backend failure" in item.failure_categories
    assert "proof verification failure" in item.failure_categories
    assert item.failure_reason == "TimeoutError: fixture provider timeout"
    assert result.average_formalization_attempts == 1
    assert result.average_proof_attempts == 1
    assert result.token_usage == TokenUsage(2, 4, 6)


def test_nonmatching_statements_are_unknown_not_inequivalent() -> None:
    assert compare_statements(
        "theorem reference (n : ℕ) : n + 0 = n",
        "theorem generated (n : ℕ) : n + 0 = n",
    ) == "exact_match"
    assert compare_statements(
        "theorem reference (n : ℕ) : n + 0 = n",
        "theorem generated (n : ℕ) : n = n",
    ) == "unknown"
    assert compare_statements("theorem reference : True", None) == "unknown"


def test_human_review_is_loaded_separately_and_validated(tmp_path: Path) -> None:
    path = tmp_path / "reviews.json"
    path.write_text(
        json.dumps(
            {
                "reviews": [
                    {
                        "id": "sample",
                        "semantic_review": "incorrect",
                        "failure_categories": ["missing assumption"],
                        "notes": "Dropped the nonzero premise.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    review = load_semantic_reviews(path)["sample"]
    assert review.semantic_correct is False
    assert review.failure_categories == ("missing assumption",)
    with pytest.raises(ValueError, match="invalid semantic failure category"):
        SemanticReview("sample", "incorrect", ("made up",))


@pytest.mark.lean
def test_all_reference_statements_elaborate_as_propositions(tmp_path: Path) -> None:
    problems = load_formalization_benchmarks(BENCHMARK_DIR)
    declarations = [
        re.sub(r"^theorem\b", "axiom", problem.reference_statement, count=1)
        for problem in problems
    ]
    checks = []
    for problem in problems:
        checks.extend(
            [
                "run_cmd Lean.Elab.Command.liftTermElabM do",
                f"  let declaration ← getConstInfo ``{problem.id}",
                "  unless ← isProp declaration.type do",
                f"    throwError \"{problem.id} is not a proposition\"",
            ]
        )
    source = tmp_path / "formalization_references.lean"
    source.write_text(
        "import Mathlib\n\nset_option autoImplicit false\n\n"
        + "\n\n".join(declarations)
        + "\n\nopen Lean Meta\n\n"
        + "\n".join(checks)
        + "\n",
        encoding="utf-8",
    )
    result = LeanVerifier(ROOT).verify(source)
    assert result.success, result.compiler_feedback
