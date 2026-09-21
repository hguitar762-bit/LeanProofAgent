from __future__ import annotations

import json
from types import SimpleNamespace

from examples import run_real_model_experiment as experiment


def test_experiment_runner_supports_ollama_without_openai_key(
    monkeypatch, tmp_path
) -> None:
    captured: dict[str, object] = {}
    problem = SimpleNamespace(id="arith_add_zero")

    class FakeRunner:
        def __init__(self, *args, **kwargs) -> None:
            captured["runner_backend_name"] = kwargs["backend_name"]
            captured["runner_model"] = kwargs["model"]

        def run(self, problems):
            return SimpleNamespace(total_problems=1, problems=())

    def fake_create_backend(backend, model):
        captured["backend"] = backend
        captured["requested_model"] = model
        return object(), "local-test-model"

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(experiment, "create_backend", fake_create_backend)
    monkeypatch.setattr(
        experiment, "load_formalization_benchmarks", lambda path: (problem,)
    )
    monkeypatch.setattr(experiment, "LeanVerifier", lambda *args, **kwargs: object())
    monkeypatch.setattr(experiment, "FormalizationEvaluationRunner", FakeRunner)
    monkeypatch.setattr(experiment, "_git_commit", lambda: "abc123")
    monkeypatch.setattr(experiment, "_benchmark_hash", lambda path: "digest")
    monkeypatch.setattr(
        experiment,
        "write_experiment_bundle",
        lambda result, directory, config: captured.update(config=config),
    )

    exit_code = experiment.main(
        [
            "--backend",
            "ollama",
            "--model",
            "local-test-model",
            "--name",
            "local-smoke",
            "--experiments-root",
            str(tmp_path),
            "--ids",
            "arith_add_zero",
        ]
    )

    assert exit_code == 0
    assert captured["backend"] == "ollama"
    assert captured["runner_backend_name"] == "ollama"
    assert captured["runner_model"] == "local-test-model"
    config = captured["config"]
    assert isinstance(config, dict)
    assert config["backend"] == "ollama-http"
    assert config["model"] == "local-test-model"
    saved = json.loads((tmp_path / "local-smoke" / "config.json").read_text("utf-8"))
    assert saved["status"] == "started"
