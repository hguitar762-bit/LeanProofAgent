"""Comparison and regression analysis for saved evaluation results."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import uuid


Number = int | float


@dataclass(frozen=True, slots=True)
class MetricComparison:
    """One aggregate metric in evaluation A, evaluation B, and their delta."""

    a: Number | None
    b: Number | None
    delta: Number | None


@dataclass(frozen=True, slots=True)
class ProblemSnapshot:
    """The comparison-relevant fields saved for one theorem."""

    name: str
    category: str | None
    verified: bool | None
    attempts: int | None
    latency_seconds: float | None


@dataclass(frozen=True, slots=True)
class EvaluationSnapshot:
    """A tolerant view of one saved evaluation JSON document."""

    path: Path
    backend: str | None
    model: str | None
    max_attempts: int | None
    total_problems: int | None
    verified_problems: int | None
    verified_success_rate: float | None
    average_attempts: float | None
    average_latency_seconds: float | None
    total_tokens: int | None
    problems: dict[str, ProblemSnapshot]


@dataclass(frozen=True, slots=True)
class TheoremComparison:
    """Status and performance changes for one theorem name."""

    name: str
    category: str | None
    status: str
    attempts_a: int | None
    attempts_b: int | None
    attempts_delta: int | None
    latency_a_seconds: float | None
    latency_b_seconds: float | None
    latency_delta_seconds: float | None


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    """Aggregate and per-theorem differences between two evaluations."""

    evaluation_a: EvaluationSnapshot
    evaluation_b: EvaluationSnapshot
    metrics: dict[str, MetricComparison]
    common_problems: int
    only_in_a: tuple[str, ...]
    only_in_b: tuple[str, ...]
    newly_solved: tuple[str, ...]
    regressions: tuple[str, ...]
    still_failed: tuple[str, ...]
    per_theorem: tuple[TheoremComparison, ...]


def load_evaluation(path: Path) -> EvaluationSnapshot:
    """Load the fields needed for comparison without inventing missing data."""

    resolved = path.expanduser().resolve()
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid evaluation JSON {resolved}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"evaluation JSON must contain an object: {resolved}")

    raw_problems = payload.get("problems")
    if not isinstance(raw_problems, list):
        raise ValueError(f"evaluation JSON has no problems list: {resolved}")
    problems: dict[str, ProblemSnapshot] = {}
    for index, raw in enumerate(raw_problems):
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
            raise ValueError(f"invalid problem at index {index} in {resolved}")
        name = raw["name"]
        if name in problems:
            raise ValueError(f"duplicate problem name {name!r} in {resolved}")
        problems[name] = ProblemSnapshot(
            name=name,
            category=_string(raw.get("category")),
            verified=raw.get("verified") if isinstance(raw.get("verified"), bool) else None,
            attempts=_integer(raw.get("attempts")),
            latency_seconds=_float(raw.get("latency_seconds")),
        )

    token_usage = payload.get("token_usage")
    total_tokens = None
    if isinstance(token_usage, dict):
        total_tokens = _integer(token_usage.get("total_tokens"))

    return EvaluationSnapshot(
        path=resolved,
        backend=_string(payload.get("backend")),
        model=_string(payload.get("model")),
        max_attempts=_integer(payload.get("max_attempts")),
        total_problems=_integer(payload.get("total_problems")),
        verified_problems=_integer(payload.get("verified_problems")),
        verified_success_rate=_float(payload.get("verified_success_rate")),
        average_attempts=_float(payload.get("average_attempts")),
        average_latency_seconds=_float(payload.get("average_latency_seconds")),
        total_tokens=total_tokens,
        problems=problems,
    )


def compare_evaluations(path_a: Path, path_b: Path) -> ComparisonResult:
    """Compare two saved evaluation files, matching theorems by name."""

    a = load_evaluation(path_a)
    b = load_evaluation(path_b)
    names_a = set(a.problems)
    names_b = set(b.problems)
    common = names_a & names_b
    only_a = tuple(sorted(names_a - names_b))
    only_b = tuple(sorted(names_b - names_a))

    rows: list[TheoremComparison] = []
    for name in sorted(names_a | names_b):
        problem_a = a.problems.get(name)
        problem_b = b.problems.get(name)
        rows.append(_compare_problem(name, problem_a, problem_b))

    metrics = {
        "success_rate": _metric(
            a.verified_success_rate, b.verified_success_rate
        ),
        "verified_problems": _metric(a.verified_problems, b.verified_problems),
        "average_attempts": _metric(a.average_attempts, b.average_attempts),
        "average_latency_seconds": _metric(
            a.average_latency_seconds, b.average_latency_seconds
        ),
        "total_tokens": _metric(a.total_tokens, b.total_tokens),
    }
    return ComparisonResult(
        evaluation_a=a,
        evaluation_b=b,
        metrics=metrics,
        common_problems=len(common),
        only_in_a=only_a,
        only_in_b=only_b,
        newly_solved=_names_with_status(rows, "newly_solved"),
        regressions=_names_with_status(rows, "regression"),
        still_failed=_names_with_status(rows, "still_failed"),
        per_theorem=tuple(rows),
    )


def render_terminal(result: ComparisonResult) -> str:
    """Render the concise summary printed by the CLI."""

    metrics = result.metrics
    lines = [
        "LeanProofAgent Evaluation Comparison",
        f"Coverage: {result.common_problems} common, "
        f"{len(result.only_in_a)} only in A, {len(result.only_in_b)} only in B",
        f"Success rate delta: {_format_delta(metrics['success_rate'], 'rate')}",
        f"Verified problems delta: {_format_delta(metrics['verified_problems'], 'int')}",
        f"Average attempts delta: {_format_delta(metrics['average_attempts'], 'float')}",
        f"Average latency delta: {_format_delta(metrics['average_latency_seconds'], 'seconds')}",
        f"Token usage delta: {_format_delta(metrics['total_tokens'], 'int')}",
        f"Newly solved ({len(result.newly_solved)}): {_names(result.newly_solved)}",
        f"Regressions ({len(result.regressions)}): {_names(result.regressions)}",
        f"Still failed ({len(result.still_failed)}): {_names(result.still_failed)}",
    ]
    return "\n".join(lines) + "\n"


def render_markdown(result: ComparisonResult) -> str:
    """Render the complete Markdown comparison report."""

    a = result.evaluation_a
    b = result.evaluation_b
    lines = [
        "# LeanProofAgent Evaluation Comparison",
        "",
        f"- Evaluation A: `{a.path}`",
        f"- Evaluation B: `{b.path}`",
        f"- A configuration: {_configuration(a)}",
        f"- B configuration: {_configuration(b)}",
        f"- Benchmark coverage: {result.common_problems} common, "
        f"{len(result.only_in_a)} only in A, {len(result.only_in_b)} only in B",
        "",
        "## Aggregate Metrics",
        "",
        "| Metric | A | B | Delta (B - A) |",
        "|---|---:|---:|---:|",
    ]
    metric_rows = (
        ("Success rate", "success_rate", "rate"),
        ("Verified problems", "verified_problems", "int"),
        ("Average attempts", "average_attempts", "float"),
        ("Average latency", "average_latency_seconds", "seconds"),
        ("Token usage", "total_tokens", "int"),
    )
    for label, key, kind in metric_rows:
        metric = result.metrics[key]
        lines.append(
            f"| {label} | {_format_value(metric.a, kind)} | "
            f"{_format_value(metric.b, kind)} | {_format_delta(metric, kind)} |"
        )

    lines.extend(
        [
            "",
            "## Regression Summary",
            "",
            f"- Newly solved ({len(result.newly_solved)}): {_names(result.newly_solved)}",
            f"- Regressions ({len(result.regressions)}): {_names(result.regressions)}",
            f"- Still failed ({len(result.still_failed)}): {_names(result.still_failed)}",
            f"- Only in A ({len(result.only_in_a)}): {_names(result.only_in_a)}",
            f"- Only in B ({len(result.only_in_b)}): {_names(result.only_in_b)}",
            "",
            "## Per-Theorem Changes",
            "",
            "| Problem | Category | Status | Attempts A | Attempts B | Attempts Δ | Latency A | Latency B | Latency Δ |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in result.per_theorem:
        lines.append(
            f"| {_cell(row.name)} | {_cell(row.category or 'unavailable')} | "
            f"{row.status.replace('_', ' ')} | "
            f"{_format_value(row.attempts_a, 'int')} | "
            f"{_format_value(row.attempts_b, 'int')} | "
            f"{_signed(row.attempts_delta, 'int')} | "
            f"{_format_value(row.latency_a_seconds, 'seconds')} | "
            f"{_format_value(row.latency_b_seconds, 'seconds')} | "
            f"{_signed(row.latency_delta_seconds, 'seconds')} |"
        )
    return "\n".join(lines) + "\n"


def write_comparison(
    result: ComparisonResult,
    output_root: Path,
    *,
    write_json: bool = False,
) -> tuple[Path, Path | None]:
    """Write a Markdown report and, when requested, a JSON result."""

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = output_root.resolve() / f"{stamp}-comparison-{uuid.uuid4().hex[:8]}"
    output_dir.mkdir(parents=True, exist_ok=False)
    markdown_path = output_dir / "comparison.md"
    markdown_path.write_text(render_markdown(result), encoding="utf-8")
    json_path = output_dir / "comparison.json" if write_json else None
    if json_path:
        json_path.write_text(
            json.dumps(_json_payload(result), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return markdown_path, json_path


def _compare_problem(
    name: str,
    a: ProblemSnapshot | None,
    b: ProblemSnapshot | None,
) -> TheoremComparison:
    if a is None:
        status = "only_in_b"
    elif b is None:
        status = "only_in_a"
    elif a.verified is False and b.verified is True:
        status = "newly_solved"
    elif a.verified is True and b.verified is False:
        status = "regression"
    elif a.verified is False and b.verified is False:
        status = "still_failed"
    elif a.verified is True and b.verified is True:
        status = "still_solved"
    else:
        status = "unavailable"
    attempts_a = a.attempts if a else None
    attempts_b = b.attempts if b else None
    latency_a = a.latency_seconds if a else None
    latency_b = b.latency_seconds if b else None
    return TheoremComparison(
        name=name,
        category=(b.category if b and b.category else a.category if a else None),
        status=status,
        attempts_a=attempts_a,
        attempts_b=attempts_b,
        attempts_delta=_difference(attempts_a, attempts_b),
        latency_a_seconds=latency_a,
        latency_b_seconds=latency_b,
        latency_delta_seconds=_difference(latency_a, latency_b),
    )


def _metric(a: Number | None, b: Number | None) -> MetricComparison:
    return MetricComparison(a=a, b=b, delta=_difference(a, b))


def _difference(a: Number | None, b: Number | None) -> Number | None:
    return None if a is None or b is None else b - a


def _names_with_status(
    rows: list[TheoremComparison], status: str
) -> tuple[str, ...]:
    return tuple(row.name for row in rows if row.status == status)


def _format_value(value: Number | None, kind: str) -> str:
    if value is None:
        return "unavailable"
    if kind == "rate":
        return f"{value * 100:.1f}%"
    if kind == "seconds":
        return f"{value:.2f}s"
    if kind == "float":
        return f"{value:.2f}"
    return str(int(value))


def _format_delta(metric: MetricComparison, kind: str) -> str:
    if metric.delta is None:
        return "unavailable"
    if kind == "rate":
        return f"{metric.delta * 100:+.1f} pp"
    return _signed(metric.delta, kind)


def _signed(value: Number | None, kind: str) -> str:
    if value is None:
        return "unavailable"
    if kind == "seconds":
        return f"{value:+.2f}s"
    if kind == "float":
        return f"{value:+.2f}"
    return f"{int(value):+d}"


def _configuration(evaluation: EvaluationSnapshot) -> str:
    return (
        f"backend={evaluation.backend or 'unavailable'}, "
        f"model={evaluation.model or 'unavailable'}, "
        f"max_attempts={evaluation.max_attempts if evaluation.max_attempts is not None else 'unavailable'}"
    )


def _names(values: tuple[str, ...]) -> str:
    return ", ".join(values) if values else "none"


def _cell(value: str) -> str:
    return value.replace("|", "\\|")


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _json_payload(result: ComparisonResult) -> dict[str, Any]:
    payload = asdict(result)
    payload["evaluation_a"]["path"] = str(result.evaluation_a.path)
    payload["evaluation_b"]["path"] = str(result.evaluation_b.path)
    return payload
