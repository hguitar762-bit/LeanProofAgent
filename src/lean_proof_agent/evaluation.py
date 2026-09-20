"""Sequential benchmark evaluation built on the existing proof agent."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from statistics import fmean, median
import time
import uuid

from .agent import ProofAgent, ProofVerifier
from .llm import LLMBackend
from .models import LeanProblem, RunResult, TokenUsage


@dataclass(frozen=True, slots=True)
class EvaluationProblemResult:
    """Machine-readable outcome for one independently executed theorem."""

    name: str
    category: str
    verified: bool
    attempts: int
    latency_seconds: float
    final_proof: str | None
    failure_reason: str | None
    token_usage: TokenUsage | None
    token_usage_reported_attempts: int
    run_dir: str | None


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """Aggregate metrics and all per-problem outcomes."""

    backend: str
    model: str | None
    max_attempts: int
    total_problems: int
    verified_problems: int
    verified_success_rate: float
    average_attempts: float
    median_attempts: float
    average_latency_seconds: float
    total_latency_seconds: float
    token_usage: TokenUsage | None
    token_usage_reported_attempts: int
    problems: tuple[EvaluationProblemResult, ...]
    evaluation_dir: Path


class EvaluationRunner:
    """Run every problem sequentially while isolating per-problem failures."""

    def __init__(
        self,
        backend: LLMBackend,
        verifier: ProofVerifier,
        *,
        max_attempts: int = 3,
        output_root: Path = Path("evaluations"),
        backend_name: str = "custom",
        model: str | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.backend = backend
        self.verifier = verifier
        self.max_attempts = max_attempts
        self.output_root = output_root
        self.backend_name = backend_name
        self.model = model

    def run(self, problems: tuple[LeanProblem, ...]) -> EvaluationResult:
        if not problems:
            raise ValueError("evaluation requires at least one problem")
        _reject_duplicate_names(problems)
        evaluation_dir = _create_evaluation_dir(self.output_root)
        problem_artifacts = evaluation_dir / "problems"
        outcomes: list[EvaluationProblemResult] = []

        for problem in problems:
            started = time.monotonic()
            try:
                run_result = ProofAgent(
                    self.backend,
                    self.verifier,
                    max_attempts=self.max_attempts,
                    artifacts_root=problem_artifacts,
                ).solve(problem)
            except Exception as exc:  # isolate one theorem/backend failure
                latency = time.monotonic() - started
                outcomes.append(
                    EvaluationProblemResult(
                        name=problem.name,
                        category=problem.category,
                        verified=False,
                        attempts=0,
                        latency_seconds=latency,
                        final_proof=None,
                        failure_reason=f"{type(exc).__name__}: {exc}",
                        token_usage=None,
                        token_usage_reported_attempts=0,
                        run_dir=None,
                    )
                )
                continue

            latency = time.monotonic() - started
            outcomes.append(_problem_outcome(run_result, latency))

        result = _aggregate(
            tuple(outcomes),
            evaluation_dir,
            backend=self.backend_name,
            model=self.model,
            max_attempts=self.max_attempts,
        )
        write_evaluation(result)
        return result


def _problem_outcome(
    result: RunResult, latency_seconds: float
) -> EvaluationProblemResult:
    failure_reason = None
    if not result.success:
        failure_reason = (
            result.attempts[-1].verification.compiler_feedback
            if result.attempts
            else "No proof attempt was completed."
        )
    return EvaluationProblemResult(
        name=result.problem.name,
        category=result.problem.category,
        verified=result.success,
        attempts=len(result.attempts),
        latency_seconds=latency_seconds,
        final_proof=result.final_proof,
        failure_reason=failure_reason,
        token_usage=result.token_usage,
        token_usage_reported_attempts=sum(
            item.token_usage is not None for item in result.attempts
        ),
        run_dir=str(result.run_dir),
    )


def _aggregate(
    problems: tuple[EvaluationProblemResult, ...],
    evaluation_dir: Path,
    *,
    backend: str,
    model: str | None,
    max_attempts: int,
) -> EvaluationResult:
    total = len(problems)
    verified = sum(item.verified for item in problems)
    attempts = [item.attempts for item in problems]
    latencies = [item.latency_seconds for item in problems]
    usages = [item.token_usage for item in problems if item.token_usage]
    token_usage = None
    if usages:
        token_usage = TokenUsage(0, 0, 0)
        for usage in usages:
            token_usage += usage
    return EvaluationResult(
        backend=backend,
        model=model,
        max_attempts=max_attempts,
        total_problems=total,
        verified_problems=verified,
        verified_success_rate=verified / total,
        average_attempts=fmean(attempts),
        median_attempts=float(median(attempts)),
        average_latency_seconds=fmean(latencies),
        total_latency_seconds=sum(latencies),
        token_usage=token_usage,
        token_usage_reported_attempts=sum(
            item.token_usage_reported_attempts for item in problems
        ),
        problems=problems,
        evaluation_dir=evaluation_dir,
    )


def write_evaluation(result: EvaluationResult) -> None:
    payload = asdict(result)
    payload["evaluation_dir"] = str(result.evaluation_dir)
    (result.evaluation_dir / "evaluation.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (result.evaluation_dir / "summary.md").write_text(
        render_markdown(result), encoding="utf-8"
    )


def render_markdown(result: EvaluationResult) -> str:
    """Render a concise human-readable report and problem table."""

    lines = [
        "# LeanProofAgent Evaluation",
        "",
        f"- Backend: {result.backend}",
        f"- Model: {result.model or 'not applicable'}",
        f"- Maximum attempts: {result.max_attempts}",
        f"- Problems: {result.total_problems}",
        f"- Verified: {result.verified_problems}",
        f"- Success rate: {result.verified_success_rate * 100:.1f}%",
        f"- Average attempts: {result.average_attempts:.2f}",
        f"- Median attempts: {result.median_attempts:g}",
        f"- Average latency: {result.average_latency_seconds:.2f}s",
        f"- Total latency: {result.total_latency_seconds:.2f}s",
    ]
    if result.token_usage:
        total_attempts = sum(item.attempts for item in result.problems)
        lines.append(
            f"- Total tokens: {result.token_usage.total_tokens} "
            f"(reported for {result.token_usage_reported_attempts}/{total_attempts} attempts)"
        )
    else:
        lines.append("- Total tokens: unavailable")
    lines.extend(
        [
            "",
            "| Problem | Category | Status | Attempts | Latency | Tokens | Failure |",
            "|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for item in result.problems:
        status = "verified" if item.verified else "failed"
        tokens = str(item.token_usage.total_tokens) if item.token_usage else "—"
        failure = _one_line(item.failure_reason) if item.failure_reason else "—"
        lines.append(
            f"| {_cell(item.name)} | {_cell(item.category)} | {status} | "
            f"{item.attempts} | {item.latency_seconds:.2f}s | {tokens} | "
            f"{_cell(failure)} |"
        )
    return "\n".join(lines) + "\n"


def _create_evaluation_dir(root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = root.resolve() / f"{stamp}-evaluation-{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def _reject_duplicate_names(problems: tuple[LeanProblem, ...]) -> None:
    names = [problem.name for problem in problems]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"duplicate benchmark name(s): {', '.join(duplicates)}")


def _one_line(value: str) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    return compact if len(compact) <= 160 else compact[:157] + "..."


def _cell(value: str) -> str:
    return value.replace("|", "\\|")
