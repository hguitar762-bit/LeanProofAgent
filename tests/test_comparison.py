from __future__ import annotations

import json
from pathlib import Path

import pytest

from lean_proof_agent.cli import main
from lean_proof_agent.comparison import (
    compare_evaluations,
    render_markdown,
    render_terminal,
    write_comparison,
)


def _write_evaluation(
    path: Path,
    *,
    success_rate: float | None,
    verified: int | None,
    average_attempts: float | None,
    average_latency: float | None,
    total_tokens: int | None,
    problems: list[dict[str, object]],
) -> None:
    payload: dict[str, object] = {
        "backend": "fixture",
        "model": "test-model",
        "max_attempts": 3,
        "total_problems": len(problems),
        "verified_success_rate": success_rate,
        "verified_problems": verified,
        "average_attempts": average_attempts,
        "average_latency_seconds": average_latency,
        "token_usage": (
            {"input_tokens": 0, "output_tokens": 0, "total_tokens": total_tokens}
            if total_tokens is not None
            else None
        ),
        "problems": problems,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _problem(
    name: str, verified: bool, attempts: int, latency: float
) -> dict[str, object]:
    return {
        "name": name,
        "category": "logic",
        "verified": verified,
        "attempts": attempts,
        "latency_seconds": latency,
    }


def test_comparison_reports_regressions_deltas_and_partial_coverage(
    tmp_path: Path,
) -> None:
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    _write_evaluation(
        path_a,
        success_rate=0.6,
        verified=3,
        average_attempts=1.8,
        average_latency=3.0,
        total_tokens=120,
        problems=[
            _problem("new", False, 3, 4.0),
            _problem("only_a", True, 1, 3.0),
            _problem("regressed", True, 1, 2.0),
            _problem("shared", True, 1, 1.0),
            _problem("still_failed", False, 3, 5.0),
        ],
    )
    _write_evaluation(
        path_b,
        success_rate=0.4,
        verified=2,
        average_attempts=2.4,
        average_latency=3.5,
        total_tokens=150,
        problems=[
            _problem("new", True, 2, 3.0),
            _problem("only_b", False, 3, 4.0),
            _problem("regressed", False, 3, 6.0),
            _problem("shared", True, 2, 0.5),
            _problem("still_failed", False, 3, 4.0),
        ],
    )

    result = compare_evaluations(path_a, path_b)

    assert result.common_problems == 4
    assert result.only_in_a == ("only_a",)
    assert result.only_in_b == ("only_b",)
    assert result.newly_solved == ("new",)
    assert result.regressions == ("regressed",)
    assert result.still_failed == ("still_failed",)
    assert result.metrics["success_rate"].delta == pytest.approx(-0.2)
    assert result.metrics["verified_problems"].delta == -1
    assert result.metrics["average_attempts"].delta == pytest.approx(0.6)
    assert result.metrics["average_latency_seconds"].delta == pytest.approx(0.5)
    assert result.metrics["total_tokens"].delta == 30

    shared = next(row for row in result.per_theorem if row.name == "shared")
    assert shared.attempts_delta == 1
    assert shared.latency_delta_seconds == pytest.approx(-0.5)
    only_b = next(row for row in result.per_theorem if row.name == "only_b")
    assert only_b.status == "only_in_b"
    assert only_b.attempts_delta is None

    terminal = render_terminal(result)
    assert "Success rate delta: -20.0 pp" in terminal
    assert "Token usage delta: +30" in terminal
    report = render_markdown(result)
    assert "| regressed | logic | regression |" in report
    assert "Only in B (1): only_b" in report

    markdown_path, json_path = write_comparison(
        result, tmp_path / "reports", write_json=True
    )
    assert markdown_path.is_file()
    assert json_path is not None and json_path.is_file()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["regressions"] == ["regressed"]
    assert payload["metrics"]["total_tokens"]["delta"] == 30


def test_missing_metrics_remain_unavailable(tmp_path: Path) -> None:
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    _write_evaluation(
        path_a,
        success_rate=1.0,
        verified=1,
        average_attempts=None,
        average_latency=1.0,
        total_tokens=None,
        problems=[_problem("same", True, 1, 1.0)],
    )
    _write_evaluation(
        path_b,
        success_rate=1.0,
        verified=1,
        average_attempts=1.0,
        average_latency=2.0,
        total_tokens=10,
        problems=[_problem("same", True, 1, 2.0)],
    )

    result = compare_evaluations(path_a, path_b)

    assert result.metrics["average_attempts"].delta is None
    assert result.metrics["total_tokens"].delta is None
    assert "Average attempts delta: unavailable" in render_terminal(result)
    assert "| Token usage | unavailable | 10 | unavailable |" in render_markdown(
        result
    )


def test_compare_cli_writes_markdown_and_optional_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    for path, latency in ((path_a, 1.0), (path_b, 2.0)):
        _write_evaluation(
            path,
            success_rate=1.0,
            verified=1,
            average_attempts=1.0,
            average_latency=latency,
            total_tokens=None,
            problems=[_problem("same", True, 1, latency)],
        )

    output_root = tmp_path / "comparisons"
    assert main(
        [
            "compare",
            str(path_a),
            str(path_b),
            "--output-dir",
            str(output_root),
            "--json",
        ]
    ) == 0

    output = capsys.readouterr().out
    assert "Average latency delta: +1.00s" in output
    assert len(list(output_root.glob("*/comparison.md"))) == 1
    assert len(list(output_root.glob("*/comparison.json"))) == 1


def test_comparison_rejects_duplicate_problem_names(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    _write_evaluation(
        path,
        success_rate=0.0,
        verified=0,
        average_attempts=1.0,
        average_latency=1.0,
        total_tokens=None,
        problems=[_problem("same", False, 1, 1.0)] * 2,
    )

    with pytest.raises(ValueError, match="duplicate problem name"):
        compare_evaluations(path, path)
