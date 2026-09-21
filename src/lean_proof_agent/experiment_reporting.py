"""Write reproducible real-model experiment bundles from evaluation results."""

from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path

from .formalization_evaluation import (
    FormalizationEvaluationResult,
    FormalizationProblemResult,
)


def write_experiment_bundle(
    result: FormalizationEvaluationResult,
    experiment_dir: Path,
    config: dict[str, object],
) -> None:
    """Write config, full results, summary, and categorized failures."""

    payload = asdict(result)
    payload["evaluation_dir"] = _portable_path(result.evaluation_dir, experiment_dir)
    for problem in payload["problems"]:
        for key in ("run_dir", "equivalence_run_dir"):
            if problem[key]:
                problem[key] = _portable_path(Path(problem[key]), experiment_dir)
    documents = {
        "config.json": json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        "results.json": json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        "summary.md": render_experiment_summary(result, config),
        "failures.md": render_failures(result),
    }
    _reject_secret_leak(documents)
    for name, content in documents.items():
        (experiment_dir / name).write_text(content, encoding="utf-8")


def render_experiment_summary(
    result: FormalizationEvaluationResult, config: dict[str, object]
) -> str:
    usage = result.token_usage
    token_text = (
        f"{usage.total_tokens} total "
        f"({usage.input_tokens} input, {usage.output_tokens} output)"
        if usage
        else "unavailable"
    )
    return "\n".join(
        [
            "# Real-model Autoformalization Baseline",
            "",
            "## Configuration",
            "",
            f"- Timestamp (UTC): {config['timestamp_utc']}",
            f"- Git commit: `{config['git_commit']}`",
            f"- Backend/model: {config['backend']} / {config['model']}",
            f"- Problems: {result.total_problems}",
            f"- Formalization attempts: {result.max_formalization_attempts}",
            f"- Proof attempts: {result.max_proof_attempts}",
            f"- Equivalence attempts per direction: {result.max_equivalence_attempts}",
            "",
            "## Results",
            "",
            f"- First-pass formalization: {result.first_formalization_successes}/{result.total_problems} ({_pct(result.first_formalization_success_rate)})",
            f"- Final formalization: {result.well_formed_problems}/{result.total_problems} ({_pct(result.statement_success_rate)})",
            f"- Formalization repair gain: +{result.formalization_repair_gain_count} problems (+{result.formalization_repair_gain_percentage_points:.1f} pp)",
            f"- First-pass proof: {result.first_proof_successes}/{result.total_problems} ({_pct(result.first_proof_success_rate)})",
            f"- Final proof: {result.proof_verified_problems}/{result.total_problems} ({_pct(result.end_to_end_proof_verification_rate)})",
            f"- Proof repair gain: +{result.proof_repair_gain_count} problems (+{result.proof_repair_gain_percentage_points:.1f} pp)",
            f"- Semantic equivalent: {result.equivalent_problems}/{result.total_problems} ({_pct(result.semantic_equivalence_rate)})",
            f"- Semantic unknown: {result.semantic_unknown_problems}/{result.total_problems} ({_pct(result.semantic_unknown_rate)})",
            f"- Semantic not_equivalent: {result.semantic_not_equivalent_problems}/{result.total_problems}",
            f"- Average formalization attempts: {result.average_formalization_attempts:.2f}",
            f"- Average proof attempts: {result.average_proof_attempts:.2f}",
            f"- Average latency: {result.average_latency_seconds:.2f}s",
            f"- Total latency: {result.total_latency_seconds:.2f}s",
            f"- Provider-reported token usage: {token_text}",
            f"- Attempts with reported usage: {result.token_usage_reported_attempts}",
            "",
            "## Interpretation boundary",
            "",
            "Compiler-verified provability and Lean equivalence are not human semantic correctness. Equivalence proof-search failures remain unknown.",
            "",
        ]
    )


def render_failures(result: FormalizationEvaluationResult) -> str:
    groups: dict[str, list[FormalizationProblemResult]] = {}
    for problem in result.problems:
        for category in problem.failure_categories:
            groups.setdefault(category, []).append(problem)
    lines = [
        "# Failure Analysis",
        "",
        "Semantic categories come only from human review; automatic unknown remains unknown.",
        "",
    ]
    if not groups:
        lines.extend(["No failures were recorded.", ""])
        return "\n".join(lines)
    for category, problems in sorted(groups.items()):
        lines.extend([f"## {category}", ""])
        for problem in problems[:5]:
            feedback = _feedback(problem)
            lines.extend(
                [
                    f"### {problem.id}",
                    "",
                    f"- Natural language: {problem.natural_language}",
                    f"- Reference statement: `{_one_line(problem.reference_statement)}`",
                    f"- Generated statement: `{_one_line(problem.generated_statement) if problem.generated_statement else 'unavailable'}`",
                    f"- Lean feedback: {feedback}",
                    f"- Final result: well_formed={problem.well_formed}, verified={problem.proof_verified}, equivalence={problem.equivalence_result}",
                    "",
                ]
            )
    return "\n".join(lines)


def _feedback(problem: FormalizationProblemResult) -> str:
    values = [
        problem.formalization_feedback,
        problem.proof_feedback,
        problem.equivalence_forward_error,
        problem.equivalence_backward_error,
        problem.failure_reason,
    ]
    compact = [_one_line(value) for value in values if value]
    return " | ".join(dict.fromkeys(compact)) if compact else "unavailable"


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _one_line(value: str) -> str:
    return " ".join(value.split()).replace("`", "'")


def _reject_secret_leak(documents: dict[str, str]) -> None:
    key = os.environ.get("OPENAI_API_KEY")
    if key and any(key in content for content in documents.values()):
        raise RuntimeError("refusing to write an experiment artifact containing API key")


def _portable_path(path: Path, experiment_dir: Path) -> str:
    try:
        return str(path.resolve().relative_to(experiment_dir.resolve()))
    except ValueError:
        return str(path)
