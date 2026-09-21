"""Semantic-aware evaluation for natural-language autoformalization."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from statistics import fmean
import time
import uuid

from .agent import ProofVerifier
from .formalization import AutoformalizationAgent, StatementVerifier
from .formalization_benchmarks import FormalizationBenchmark
from .llm import LLMBackend
from .semantic_equivalence import SemanticEquivalenceChecker


SEMANTIC_REVIEW_STATUSES = frozenset(
    {"correct", "incorrect", "ambiguous", "unreviewed"}
)
SEMANTIC_FAILURE_CATEGORIES = frozenset(
    {
        "missing assumption",
        "stronger statement",
        "weaker statement",
        "wrong quantifier",
        "wrong type/domain",
        "wrong implication direction",
        "ambiguity",
    }
)


@dataclass(frozen=True, slots=True)
class SemanticReview:
    id: str
    semantic_review: str = "unreviewed"
    failure_categories: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        if self.semantic_review not in SEMANTIC_REVIEW_STATUSES:
            raise ValueError(f"invalid semantic review status: {self.semantic_review}")
        invalid = sorted(set(self.failure_categories) - SEMANTIC_FAILURE_CATEGORIES)
        if invalid:
            raise ValueError(f"invalid semantic failure category: {', '.join(invalid)}")

    @property
    def semantic_correct(self) -> bool | None:
        if self.semantic_review == "correct":
            return True
        if self.semantic_review == "incorrect":
            return False
        return None


@dataclass(frozen=True, slots=True)
class FormalizationProblemResult:
    id: str
    category: str
    natural_language: str
    reference_statement: str
    generated_statement: str | None
    assumptions: tuple[str, ...]
    ambiguity_notes: str
    well_formed: bool
    provable: bool
    proof_verified: bool
    formalization_attempts: int
    repair_attempted: bool
    repair_succeeded: bool
    comparison: str
    equivalence_forward: str
    equivalence_backward: str
    equivalence_result: str
    equivalence_run_dir: str | None
    semantic_review: str
    semantic_correct: bool | None
    review_notes: str
    failure_categories: tuple[str, ...]
    failure_reason: str | None
    run_dir: str | None
    latency_seconds: float


@dataclass(frozen=True, slots=True)
class FormalizationEvaluationResult:
    backend: str
    model: str | None
    max_formalization_attempts: int
    max_proof_attempts: int
    max_equivalence_attempts: int
    total_problems: int
    well_formed_problems: int
    statement_success_rate: float
    repair_opportunities: int
    repair_successes: int
    repair_success_rate: float | None
    average_formalization_attempts: float
    proof_verified_problems: int
    end_to_end_proof_verification_rate: float
    equivalent_problems: int
    semantic_review_counts: dict[str, int]
    failure_categories: dict[str, int]
    problems: tuple[FormalizationProblemResult, ...]
    evaluation_dir: Path


class FormalizationEvaluationRunner:
    """Run autoformalization, proof verification, and review-aware reporting."""

    def __init__(
        self,
        backend: LLMBackend,
        statement_verifier: StatementVerifier,
        proof_verifier: ProofVerifier,
        *,
        max_formalization_attempts: int = 3,
        max_proof_attempts: int = 3,
        max_equivalence_attempts: int = 2,
        output_root: Path = Path("formalization_evaluations"),
        backend_name: str = "custom",
        model: str | None = None,
        reviews: dict[str, SemanticReview] | None = None,
    ) -> None:
        if min(
            max_formalization_attempts, max_proof_attempts, max_equivalence_attempts
        ) < 1:
            raise ValueError("attempt limits must be at least 1")
        self.backend = backend
        self.statement_verifier = statement_verifier
        self.proof_verifier = proof_verifier
        self.max_formalization_attempts = max_formalization_attempts
        self.max_proof_attempts = max_proof_attempts
        self.max_equivalence_attempts = max_equivalence_attempts
        self.output_root = output_root
        self.backend_name = backend_name
        self.model = model
        self.reviews = reviews or {}

    def run(
        self, problems: tuple[FormalizationBenchmark, ...]
    ) -> FormalizationEvaluationResult:
        if not problems:
            raise ValueError("formalization evaluation requires at least one problem")
        _reject_unknown_reviews(problems, self.reviews)
        evaluation_dir = _create_evaluation_dir(self.output_root)
        outcomes: list[FormalizationProblemResult] = []
        for benchmark in problems:
            review = self.reviews.get(benchmark.id, SemanticReview(benchmark.id))
            started = time.monotonic()
            try:
                result = AutoformalizationAgent(
                    self.backend,
                    self.statement_verifier,
                    self.proof_verifier,
                    max_formalization_attempts=self.max_formalization_attempts,
                    max_proof_attempts=self.max_proof_attempts,
                    artifacts_root=evaluation_dir / "problems",
                    imports=benchmark.imports,
                ).solve(benchmark.natural_language_problem())
            except Exception as exc:  # isolate provider and per-problem failures
                outcomes.append(
                    _exception_outcome(
                        benchmark, review, exc, time.monotonic() - started
                    )
                )
                continue
            equivalence = None
            equivalence_error = None
            if result.final_theorem is not None:
                try:
                    equivalence = SemanticEquivalenceChecker(
                        self.backend,
                        self.proof_verifier,
                        max_attempts=self.max_equivalence_attempts,
                        artifacts_root=evaluation_dir / "equivalence",
                    ).check(
                        benchmark.reference_statement,
                        result.final_theorem,
                        imports=benchmark.imports,
                    )
                except Exception as exc:
                    equivalence_error = f"{type(exc).__name__}: {exc}"
            outcomes.append(
                _problem_outcome(
                    benchmark,
                    review,
                    result,
                    equivalence,
                    equivalence_error,
                    time.monotonic() - started,
                )
            )
        final = _aggregate(
            tuple(outcomes),
            evaluation_dir,
            backend=self.backend_name,
            model=self.model,
            max_formalization_attempts=self.max_formalization_attempts,
            max_proof_attempts=self.max_proof_attempts,
            max_equivalence_attempts=self.max_equivalence_attempts,
        )
        write_formalization_evaluation(final)
        return final


def compare_statements(reference: str, generated: str | None) -> str:
    """Return ``exact_match`` or conservatively return ``unknown``.

    This deliberately makes no non-equivalence claim. Whitespace and theorem
    names are ignored, but no tactic or LLM output is treated as semantic truth.
    """

    if generated is None:
        return "unknown"
    return (
        "exact_match"
        if _statement_signature(reference) == _statement_signature(generated)
        else "unknown"
    )


def load_semantic_reviews(path: Path) -> dict[str, SemanticReview]:
    """Load human decisions from an evaluation-side file, never the benchmark."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("reviews") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("semantic review file requires a 'reviews' list")
    reviews: dict[str, SemanticReview] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each semantic review must be an object")
        problem_id = row.get("id")
        status = row.get("semantic_review", "unreviewed")
        categories = row.get("failure_categories", [])
        notes = row.get("notes", "")
        if not isinstance(problem_id, str) or not isinstance(status, str):
            raise ValueError("semantic review id and status must be strings")
        if not isinstance(categories, list) or not all(
            isinstance(item, str) for item in categories
        ):
            raise ValueError("semantic review failure_categories must be strings")
        if not isinstance(notes, str):
            raise ValueError("semantic review notes must be a string")
        if problem_id in reviews:
            raise ValueError(f"duplicate semantic review id: {problem_id}")
        reviews[problem_id] = SemanticReview(
            problem_id, status, tuple(categories), notes
        )
    return reviews


def write_formalization_evaluation(result: FormalizationEvaluationResult) -> None:
    payload = asdict(result)
    payload["evaluation_dir"] = str(result.evaluation_dir)
    (result.evaluation_dir / "evaluation.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (result.evaluation_dir / "summary.md").write_text(
        render_formalization_markdown(result), encoding="utf-8"
    )
    review_payload = {
        "instructions": (
            "Human review only. Edit statuses and notes, then pass this file with "
            "--reviews. Do not copy decisions into the benchmark."
        ),
        "reviews": [
            {
                "id": item.id,
                "semantic_review": item.semantic_review,
                "failure_categories": [
                    category
                    for category in item.failure_categories
                    if category in SEMANTIC_FAILURE_CATEGORIES
                ],
                "notes": item.review_notes,
            }
            for item in result.problems
        ],
    }
    (result.evaluation_dir / "semantic_reviews.json").write_text(
        json.dumps(review_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def render_formalization_markdown(result: FormalizationEvaluationResult) -> str:
    repair_rate = (
        "not applicable"
        if result.repair_success_rate is None
        else f"{result.repair_success_rate * 100:.1f}%"
    )
    lines = [
        "# Autoformalization Evaluation",
        "",
        f"- Backend: {result.backend}",
        f"- Model: {result.model or 'not applicable'}",
        f"- Problems: {result.total_problems}",
        f"- Statement syntax/type success rate: {result.statement_success_rate * 100:.1f}%",
        f"- Repair success rate: {repair_rate} ({result.repair_successes}/{result.repair_opportunities})",
        f"- Average formalization attempts: {result.average_formalization_attempts:.2f}",
        f"- End-to-end proof verification rate: {result.end_to_end_proof_verification_rate * 100:.1f}%",
        f"- Lean-verified semantic equivalences: {result.equivalent_problems}",
        "- Semantic correctness: human review only; exact_match is not used as a review decision",
        "- Failure to prove either implication yields unknown, not not_equivalent",
        "",
        "## Failure categories",
        "",
    ]
    if result.failure_categories:
        lines.extend(
            f"- {category}: {count}"
            for category, count in sorted(result.failure_categories.items())
        )
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Problems",
            "",
            "| Problem | Natural language | Reference Lean | Generated Lean | Well formed | Proof verified | Comparison | Equivalence forward | Equivalence backward | Equivalence result | Semantic review | Notes |",
            "|---|---|---|---|---:|---:|---|---|---|---|---|---|",
        ]
    )
    for item in result.problems:
        notes = item.review_notes or item.ambiguity_notes or "—"
        lines.append(
            f"| {_cell(item.id)} | {_cell(item.natural_language)} | "
            f"`{_cell(_one_line(item.reference_statement))}` | "
            f"{_code_cell(item.generated_statement)} | "
            f"{'yes' if item.well_formed else 'no'} | "
            f"{'yes' if item.proof_verified else 'no'} | "
            f"{item.comparison} | "
            f"{item.equivalence_forward} | {item.equivalence_backward} | "
            f"{item.equivalence_result} | "
            f"{item.semantic_review} | {_cell(notes)} |"
        )
    return "\n".join(lines) + "\n"


def _problem_outcome(
    benchmark, review, result, equivalence, equivalence_error, latency
):
    attempts = result.formalization_attempts
    well_formed = result.final_problem is not None
    proof_verified = result.proof_result is not None and result.proof_result.success
    repair_attempted = len(attempts) > 1
    repair_succeeded = repair_attempted and well_formed
    categories = list(review.failure_categories)
    if equivalence_error:
        categories.append("equivalence checker failure")
    failure_reason = None
    if not well_formed:
        if attempts:
            categories.append(
                "Lean elaboration failure"
                if attempts[-1].verification.command
                else "statement format/safety rejection"
            )
            failure_reason = attempts[-1].verification.compiler_feedback
        else:
            categories.append("statement generation failure")
    elif not proof_verified:
        categories.append("proof verification failure")
        if result.proof_result and result.proof_result.attempts:
            failure_reason = result.proof_result.attempts[-1].verification.compiler_feedback
    return FormalizationProblemResult(
        id=benchmark.id,
        category=benchmark.category,
        natural_language=benchmark.natural_language,
        reference_statement=benchmark.reference_statement,
        generated_statement=result.final_theorem,
        assumptions=benchmark.assumptions,
        ambiguity_notes=benchmark.ambiguity_notes,
        well_formed=well_formed,
        provable=proof_verified,
        proof_verified=proof_verified,
        formalization_attempts=len(attempts),
        repair_attempted=repair_attempted,
        repair_succeeded=repair_succeeded,
        comparison=compare_statements(benchmark.reference_statement, result.final_theorem),
        equivalence_forward=(
            equivalence.forward.status
            if equivalence
            else "failed" if equivalence_error else "unknown"
        ),
        equivalence_backward=(
            equivalence.backward.status
            if equivalence
            else "failed" if equivalence_error else "unknown"
        ),
        equivalence_result=(equivalence.result if equivalence else "unknown"),
        equivalence_run_dir=(str(equivalence.run_dir) if equivalence else None),
        semantic_review=review.semantic_review,
        semantic_correct=review.semantic_correct,
        review_notes=review.notes,
        failure_categories=tuple(dict.fromkeys(categories)),
        failure_reason=failure_reason,
        run_dir=str(result.run_dir),
        latency_seconds=latency,
    )


def _exception_outcome(benchmark, review, exc, latency):
    categories = tuple(dict.fromkeys((*review.failure_categories, "backend failure")))
    return FormalizationProblemResult(
        id=benchmark.id,
        category=benchmark.category,
        natural_language=benchmark.natural_language,
        reference_statement=benchmark.reference_statement,
        generated_statement=None,
        assumptions=benchmark.assumptions,
        ambiguity_notes=benchmark.ambiguity_notes,
        well_formed=False,
        provable=False,
        proof_verified=False,
        formalization_attempts=0,
        repair_attempted=False,
        repair_succeeded=False,
        comparison="unknown",
        equivalence_forward="unknown",
        equivalence_backward="unknown",
        equivalence_result="unknown",
        equivalence_run_dir=None,
        semantic_review=review.semantic_review,
        semantic_correct=review.semantic_correct,
        review_notes=review.notes,
        failure_categories=categories,
        failure_reason=f"{type(exc).__name__}: {exc}",
        run_dir=None,
        latency_seconds=latency,
    )


def _aggregate(problems, evaluation_dir, **metadata):
    total = len(problems)
    well_formed = sum(item.well_formed for item in problems)
    opportunities = sum(item.repair_attempted for item in problems)
    repairs = sum(item.repair_succeeded for item in problems)
    verified = sum(item.proof_verified for item in problems)
    equivalent = sum(item.equivalence_result == "equivalent" for item in problems)
    review_counts = {status: 0 for status in sorted(SEMANTIC_REVIEW_STATUSES)}
    failure_counts: dict[str, int] = {}
    for item in problems:
        review_counts[item.semantic_review] += 1
        for category in item.failure_categories:
            failure_counts[category] = failure_counts.get(category, 0) + 1
    return FormalizationEvaluationResult(
        **metadata,
        total_problems=total,
        well_formed_problems=well_formed,
        statement_success_rate=well_formed / total,
        repair_opportunities=opportunities,
        repair_successes=repairs,
        repair_success_rate=repairs / opportunities if opportunities else None,
        average_formalization_attempts=fmean(
            item.formalization_attempts for item in problems
        ),
        proof_verified_problems=verified,
        end_to_end_proof_verification_rate=verified / total,
        equivalent_problems=equivalent,
        semantic_review_counts=review_counts,
        failure_categories=failure_counts,
        problems=problems,
        evaluation_dir=evaluation_dir,
    )


def _statement_signature(statement: str) -> str:
    without_name = re.sub(
        r"^\s*(?:theorem|example)\s+[A-Za-z_][A-Za-z0-9_']*",
        "theorem _",
        statement.strip(),
        count=1,
    )
    return re.sub(r"\s+", " ", without_name).strip()


def _reject_unknown_reviews(problems, reviews):
    known = {problem.id for problem in problems}
    unknown = sorted(set(reviews) - known)
    if unknown:
        raise ValueError(f"semantic review id(s) absent from benchmark: {', '.join(unknown)}")


def _create_evaluation_dir(root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = root.resolve() / f"{stamp}-formalization-evaluation-{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def _one_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _cell(value: str) -> str:
    return _one_line(value).replace("|", "\\|")


def _code_cell(value: str | None) -> str:
    return "—" if value is None else f"`{_cell(value)}`"
