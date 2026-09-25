"""Run a reproducible OpenAI or local Ollama baseline without mock fallback."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import subprocess

from lean_proof_agent.backends import create_backend
from lean_proof_agent.experiment_reporting import write_experiment_bundle
from lean_proof_agent.formalization_benchmarks import load_formalization_benchmarks
from lean_proof_agent.formalization_evaluation import FormalizationEvaluationRunner
from lean_proof_agent.verifier import LeanVerifier


ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a real OpenAI or local Ollama experiment with Lean."
    )
    parser.add_argument("--name", required=True)
    parser.add_argument(
        "--benchmark", type=Path, default=ROOT / "benchmarks" / "formalization"
    )
    parser.add_argument("--ids", nargs="*", help="optional smoke-test problem ids")
    parser.add_argument("--backend", choices=("openai", "ollama"), default="openai")
    parser.add_argument("--model")
    parser.add_argument(
        "--num-predict",
        type=int,
        help="Ollama-only maximum generated tokens; omitted uses the model default",
    )
    parser.add_argument("--max-formalization-attempts", type=int, default=3)
    parser.add_argument("--max-proof-attempts", type=int, default=3)
    parser.add_argument("--max-equivalence-attempts", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--experiments-root", type=Path, default=ROOT / "experiments")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.backend == "openai" and not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit(
            "OPENAI_API_KEY is not set. Set it in the current process environment; "
            "the experiment runner never reads a .env file or stores the key."
        )
    backend, model = create_backend(
        args.backend, args.model, num_predict=args.num_predict
    )
    all_problems = load_formalization_benchmarks(args.benchmark)
    problems = _select_problems(all_problems, args.ids)
    experiment_dir = args.experiments_root.resolve() / args.name
    if experiment_dir.exists():
        raise SystemExit(f"experiment directory already exists: {experiment_dir}")
    experiment_dir.mkdir(parents=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    config: dict[str, object] = {
        "schema_version": 1,
        "experiment_name": args.name,
        "status": "started",
        "timestamp_utc": timestamp,
        "git_commit": _git_commit(),
        "backend": (
            "openai-responses-api" if args.backend == "openai" else "ollama-http"
        ),
        "backend_package_version": (
            _package_version("openai") if args.backend == "openai" else None
        ),
        "model": model,
        "explicit_model_parameters": (
            {"num_predict": args.num_predict}
            if args.num_predict is not None
            else {}
        ),
        "model_parameter_note": (
            "Temperature and context length are not overridden. "
            + (
                f"Ollama num_predict is {args.num_predict}."
                if args.num_predict is not None
                else "Ollama num_predict uses the model default."
            )
        ),
        "max_formalization_attempts": args.max_formalization_attempts,
        "max_proof_attempts": args.max_proof_attempts,
        "max_equivalence_attempts_per_direction": args.max_equivalence_attempts,
        "lean_timeout_seconds": args.timeout,
        "lean_toolchain": (ROOT / "lean-toolchain").read_text("utf-8").strip(),
        "benchmark_path": _repository_path(args.benchmark),
        "benchmark_sha256": _benchmark_hash(args.benchmark),
        "problem_ids": [problem.id for problem in problems],
        "problem_count": len(problems),
    }
    (experiment_dir / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    verifier = LeanVerifier(ROOT, timeout_seconds=args.timeout)
    result = FormalizationEvaluationRunner(
        backend,
        verifier,
        verifier,
        max_formalization_attempts=args.max_formalization_attempts,
        max_proof_attempts=args.max_proof_attempts,
        max_equivalence_attempts=args.max_equivalence_attempts,
        output_root=experiment_dir / "artifacts",
        backend_name=args.backend,
        model=model,
    ).run(problems)
    provider_failures = sum(
        "backend failure" in problem.failure_categories for problem in result.problems
    )
    config["status"] = (
        "completed_with_provider_failures" if provider_failures else "completed"
    )
    config["completed_timestamp_utc"] = datetime.now(timezone.utc).isoformat()
    write_experiment_bundle(result, experiment_dir, config)
    print(f"Experiment: {experiment_dir}")
    print(f"Problems: {result.total_problems}")
    print(f"Summary: {experiment_dir / 'summary.md'}")
    return 1 if provider_failures else 0


def _select_problems(problems, ids):
    if not ids:
        return problems
    requested = set(ids)
    selected = tuple(problem for problem in problems if problem.id in requested)
    missing = sorted(requested - {problem.id for problem in selected})
    if missing:
        raise ValueError(f"unknown benchmark id(s): {', '.join(missing)}")
    return selected


def _git_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return completed.stdout.strip()


def _benchmark_hash(path: Path) -> str:
    resolved = path.resolve()
    files = [resolved] if resolved.is_file() else sorted(resolved.glob("*.json"))
    digest = hashlib.sha256()
    for item in files:
        digest.update(item.name.encode("utf-8"))
        digest.update(item.read_bytes())
    return digest.hexdigest()


def _package_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _repository_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"error: {exc}") from None
