from __future__ import annotations

import json
from pathlib import Path

import pytest

from lean_proof_agent.evaluation import EvaluationRunner, render_markdown
from lean_proof_agent.models import (
    GenerationResult,
    LeanProblem,
    TokenUsage,
    VerificationResult,
)


class MixedBackend:
    def generate(self, *, system_prompt: str, user_prompt: str) -> GenerationResult:
        if "backend_error" in user_prompt:
            raise RuntimeError("provider unavailable")
        return GenerationResult("by\n  rfl", TokenUsage(10, 5, 15))


class MixedVerifier:
    def verify(self, source_path: Path) -> VerificationResult:
        source = source_path.read_text(encoding="utf-8")
        success = "rejected" not in source
        return VerificationResult(
            success=success,
            command=("lake", "env", "lean", str(source_path)),
            exit_code=0 if success else 1,
            stdout="" if success else "error: unsolved goals",
            stderr="",
            duration_seconds=0.01,
        )


def test_evaluation_aggregates_and_isolates_failures(tmp_path: Path) -> None:
    problems = (
        LeanProblem("verified", "theorem verified : True", category="logic"),
        LeanProblem("rejected", "theorem rejected : True", category="logic"),
        LeanProblem(
            "backend_error", "theorem backend_error : True", category="logic"
        ),
    )
    result = EvaluationRunner(
        MixedBackend(),
        MixedVerifier(),
        max_attempts=1,
        output_root=tmp_path,
        backend_name="mock-test",
        model="fixture-model",
    ).run(problems)

    assert result.backend == "mock-test"
    assert result.model == "fixture-model"
    assert result.max_attempts == 1
    assert result.total_problems == 3
    assert result.verified_problems == 1
    assert result.verified_success_rate == pytest.approx(1 / 3)
    assert result.average_attempts == pytest.approx(2 / 3)
    assert result.median_attempts == 1
    assert result.total_latency_seconds >= 0
    assert result.average_latency_seconds >= 0
    assert result.token_usage == TokenUsage(20, 10, 30)
    assert result.token_usage_reported_attempts == 2
    assert [item.verified for item in result.problems] == [True, False, False]
    assert "unsolved goals" in (result.problems[1].failure_reason or "")
    assert "provider unavailable" in (result.problems[2].failure_reason or "")
    assert result.problems[0].final_proof == "by\n  rfl"

    json_path = result.evaluation_dir / "evaluation.json"
    markdown_path = result.evaluation_dir / "summary.md"
    assert json_path.is_file()
    assert markdown_path.is_file()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["total_problems"] == 3
    assert payload["problems"][0]["final_proof"] == "by\n  rfl"
    assert "Success rate: 33.3%" in render_markdown(result)


def test_evaluation_rejects_empty_suite(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one"):
        EvaluationRunner(MixedBackend(), MixedVerifier(), output_root=tmp_path).run(())
