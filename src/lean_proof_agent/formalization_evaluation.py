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
from .models import TokenUsage
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
    first_formalization_well_formed: bool
    well_formed: bool
    provable: bool
    proof_verified: bool
    formalization_attempts: int
    repair_attempted: bool
    repair_succeeded: bool
    first_proof_verified: bool
    proof_repair_attempted: bool
    proof_repair_succeeded: bool
    proof_attempts: int
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
    formalization_feedback: str | None
    proof_feedback: str | None
    equivalence_forward_error: str | None
    equivalence_backward_error: str | None
    token_usage: TokenUsage | None
    token_usage_reported_attempts: int
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
    first_formalization_successes: int
    first_formalization_success_rate: float
    well_formed_problems: int
    statement_success_rate: float
    formalization_repair_gain_count: int
    formalization_repair_gain_percentage_points: float
    repair_opportunities: int
    repair_successes: int
    repair_success_rate: float | None
    average_formalization_attempts: float
    first_proof_successes: int
    first_proof_success_rate: float
    proof_verified_problems: int
    end_to_end_proof_verification_rate: float
    proof_repair_gain_count: int
    proof_repair_gain_percentage_points: float
    average_proof_attempts: float
    equivalent_problems: int
    semantic_equivalence_rate: float
    semantic_unknown_problems: int
    semantic_unknown_rate: float
    semantic_not_equivalent_problems: int
    average_latency_seconds: float
    total_latency_seconds: float
    token_usage: TokenUsage | None
    token_usage_reported_attempts: int
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
        f"- First-pass formalization success rate: {result.first_formalization_success_rate * 100:.1f}%",
        f"- Final formalization success rate: {result.statement_success_rate * 100:.1f}%",
        f"- Formalization repair gain: +{result.formalization_repair_gain_count} problems (+{result.formalization_repair_gain_percentage_points:.1f} pp)",
        f"- Repair success rate: {repair_rate} ({result.repair_successes}/{result.repair_opportunities})",
        f"- Average formalization attempts: {result.average_formalization_attempts:.2f}",
        f"- First-pass proof success rate: {result.first_proof_success_rate * 100:.1f}%",
        f"- Final proof success rate: {result.end_to_end_proof_verification_rate * 100:.1f}%",
        f"- Proof repair gain: +{result.proof_repair_gain_count} problems (+{result.proof_repair_gain_percentage_points:.1f} pp)",
        f"- Average proof attempts: {result.average_proof_attempts:.2f}",
        f"- Lean-verified semantic equivalences: {result.equivalent_problems}",
        f"- Semantic equivalence rate: {result.semantic_equivalence_rate * 100:.1f}%",
        f"- Semantic unknown rate: {result.semantic_unknown_rate * 100:.1f}%",
        f"- Average latency: {result.average_latency_seconds:.2f}s",
        f"- Total latency: {result.total_latency_seconds:.2f}s",
        f"- Provider-reported tokens: {result.token_usage.total_tokens if result.token_usage else 'unavailable'}",
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
    first_formalization_well_formed = bool(
        attempts and attempts[0].verification.success
    )
    well_formed = result.final_problem is not None
    proof_verified = result.proof_result is not None and result.proof_result.success
    repair_attempted = len(attempts) > 1
    repair_succeeded = repair_attempted and well_formed
    proof_records = result.proof_result.attempts if result.proof_result else ()
    first_proof_verified = bool(
        proof_records and proof_records[0].verification.success
    )
    proof_repair_attempted = len(proof_records) > 1
    proof_repair_succeeded = proof_repair_attempted and proof_verified
    categories = list(review.failure_categories)
    if equivalence_error:
        categories.append("equivalence checker failure")
    failure_reason = None
    formalization_feedback = None
    proof_feedback = None
    if not well_formed:
        if attempts:
            categories.append(
                "Lean elaboration failure"
                if attempts[-1].verification.command
                else "statement format/safety rejection"
            )
            failure_reason = attempts[-1].verification.compiler_feedback
            formalization_feedback = failure_reason
        else:
            categories.append("statement generation failure")
    elif not proof_verified:
        categories.append("proof verification failure")
        if result.proof_result and result.proof_result.attempts:
            failure_reason = result.proof_result.attempts[-1].verification.compiler_feedback
            proof_feedback = failure_reason
    if equivalence and equivalence.result == "unknown":
        categories.append("semantic equivalence unknown")
    usage_records = [item.token_usage for item in attempts]
    usage_records.extend(item.token_usage for item in proof_records)
    if equivalence:
        for direction in (equivalence.forward, equivalence.backward):
            if direction.proof_result:
                usage_records.extend(
                    item.token_usage for item in direction.proof_result.attempts
                )
    token_usage = _sum_token_usage(usage_records)
    return FormalizationProblemResult(
        id=benchmark.id,
        category=benchmark.category,
        natural_language=benchmark.natural_language,
        reference_statement=benchmark.reference_statement,
        generated_statement=result.final_theorem,
        assumptions=benchmark.assumptions,
        ambiguity_notes=benchmark.ambiguity_notes,
        first_formalization_well_formed=first_formalization_well_formed,
        well_formed=well_formed,
        provable=proof_verified,
        proof_verified=proof_verified,
        formalization_attempts=len(attempts),
        repair_attempted=repair_attempted,
        repair_succeeded=repair_succeeded,
        first_proof_verified=first_proof_verified,
        proof_repair_attempted=proof_repair_attempted,
        proof_repair_succeeded=proof_repair_succeeded,
        proof_attempts=len(proof_records),
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
        formalization_feedback=formalization_feedback,
        proof_feedback=proof_feedback,
        equivalence_forward_error=(equivalence.forward.error if equivalence else None),
        equivalence_backward_error=(equivalence.backward.error if equivalence else None),
        token_usage=token_usage,
        token_usage_reported_attempts=sum(item is not None for item in usage_records),
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
        first_formalization_well_formed=False,
        well_formed=False,
        provable=False,
        proof_verified=False,
        formalization_attempts=0,
        repair_attempted=False,
        repair_succeeded=False,
        first_proof_verified=False,
        proof_repair_attempted=False,
        proof_repair_succeeded=False,
        proof_attempts=0,
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
        formalization_feedback=None,
        proof_feedback=None,
        equivalence_forward_error=None,
        equivalence_backward_error=None,
        token_usage=None,
        token_usage_reported_attempts=0,
        run_dir=None,
        latency_seconds=latency,
    )


def _aggregate(problems, evaluation_dir, **metadata):
    total = len(problems)
    first_formalized = sum(item.first_formalization_well_formed for item in problems)
    well_formed = sum(item.well_formed for item in problems)
    opportunities = sum(item.repair_attempted for item in problems)
    repairs = sum(item.repair_succeeded for item in problems)
    verified = sum(item.proof_verified for item in problems)
    first_proof = sum(item.first_proof_verified for item in problems)
    equivalent = sum(item.equivalence_result == "equivalent" for item in problems)
    unknown = sum(item.equivalence_result == "unknown" for item in problems)
    not_equivalent = sum(
        item.equivalence_result == "not_equivalent" for item in problems
    )
    token_usage = _sum_token_usage(item.token_usage for item in problems)
    review_counts = {status: 0 for status in sorted(SEMANTIC_REVIEW_STATUSES)}
    failure_counts: dict[str, int] = {}
    for item in problems:
        review_counts[item.semantic_review] += 1
        for category in item.failure_categories:
            failure_counts[category] = failure_counts.get(category, 0) + 1
    return FormalizationEvaluationResult(
        **metadata,
        total_problems=total,
        first_formalization_successes=first_formalized,
        first_formalization_success_rate=first_formalized / total,
        well_formed_problems=well_formed,
        statement_success_rate=well_formed / total,
        formalization_repair_gain_count=well_formed - first_formalized,
        formalization_repair_gain_percentage_points=(
            (well_formed - first_formalized) / total * 100
        ),
        repair_opportunities=opportunities,
        repair_successes=repairs,
        repair_success_rate=repairs / opportunities if opportunities else None,
        average_formalization_attempts=fmean(
            item.formalization_attempts for item in problems
        ),
        first_proof_successes=first_proof,
        first_proof_success_rate=first_proof / total,
        proof_verified_problems=verified,
        end_to_end_proof_verification_rate=verified / total,
        proof_repair_gain_count=verified - first_proof,
        proof_repair_gain_percentage_points=(verified - first_proof) / total * 100,
        average_proof_attempts=fmean(item.proof_attempts for item in problems),
        equivalent_problems=equivalent,
        semantic_equivalence_rate=equivalent / total,
        semantic_unknown_problems=unknown,
        semantic_unknown_rate=unknown / total,
        semantic_not_equivalent_problems=not_equivalent,
        average_latency_seconds=fmean(item.latency_seconds for item in problems),
        total_latency_seconds=sum(item.latency_seconds for item in problems),
        token_usage=token_usage,
        token_usage_reported_attempts=sum(
            item.token_usage_reported_attempts for item in problems
        ),
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


def _sum_token_usage(usages) -> TokenUsage | None:
    present = [usage for usage in usages if usage is not None]
    if not present:
        return None
    total = TokenUsage(0, 0, 0)
    for usage in present:
        total += usage
    return total


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
