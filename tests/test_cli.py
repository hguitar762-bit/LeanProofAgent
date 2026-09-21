from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from lean_proof_agent import cli


def test_solve_text_keeps_original_autoformalization_constructor(
    monkeypatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    class FakeAgent:
        def __init__(self, *args, **kwargs) -> None:
            captured.update(kwargs)

        def solve(self, problem):
            return SimpleNamespace(
                final_theorem="theorem cli_smoke : True",
                success=True,
                verified_proof="by trivial",
                final_problem=object(),
                attempts=(),
                run_dir=tmp_path,
            )

    monkeypatch.setattr(
        cli, "create_backend", lambda backend, model: (object(), model or "fixture")
    )
    monkeypatch.setattr(cli, "LeanVerifier", lambda *args, **kwargs: object())
    monkeypatch.setattr(cli, "AutoformalizationAgent", FakeAgent)
    exit_code = cli.main(
        [
            "solve-text",
            "True holds.",
            "--name",
            "cli_smoke",
            "--backend",
            "ollama",
            "--model",
            "fixture-local-model",
            "--artifacts-dir",
            str(tmp_path),
        ]
    )
    assert exit_code == 0
    assert "max_equivalence_attempts" not in captured


def test_evaluate_formalization_forwards_equivalence_attempt_limit(
    monkeypatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    class FakeRunner:
        def __init__(self, *args, **kwargs) -> None:
            captured.update(kwargs)

        def run(self, problems):
            return SimpleNamespace(evaluation_dir=tmp_path)

    monkeypatch.setattr(cli, "load_formalization_benchmarks", lambda path: (object(),))
    monkeypatch.setattr(
        cli, "create_backend", lambda backend, model: (object(), model or "fixture")
    )
    monkeypatch.setattr(cli, "LeanVerifier", lambda *args, **kwargs: object())
    monkeypatch.setattr(cli, "FormalizationEvaluationRunner", FakeRunner)
    monkeypatch.setattr(cli, "render_formalization_markdown", lambda result: "")
    exit_code = cli.main(
        [
            "evaluate-formalization",
            "--benchmark",
            str(tmp_path),
            "--max-equivalence-attempts",
            "4",
        ]
    )
    assert exit_code == 0
    assert captured["max_equivalence_attempts"] == 4
