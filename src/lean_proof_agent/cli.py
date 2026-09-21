"""Command-line interface."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .agent import ProofAgent
from .benchmarks import (
    list_benchmarks,
    load_benchmark,
    load_benchmark_paths,
    load_problem_file,
)
from .backends import create_backend
from .comparison import compare_evaluations, render_terminal, write_comparison
from .evaluation import EvaluationRunner, render_markdown
from .formalization import AutoformalizationAgent, NaturalLanguageProblem
from .formalization_benchmarks import load_formalization_benchmarks
from .formalization_evaluation import (
    FormalizationEvaluationRunner,
    load_semantic_reviews,
    render_formalization_markdown,
)
from .models import LeanProblem
from .offline_backend import OfflineMockBackend
from .semantic_equivalence import (
    SemanticEquivalenceChecker,
    load_statement_file,
    merge_imports,
    render_equivalence,
)
from .text_benchmarks import list_text_benchmarks, load_text_benchmark
from .verifier import LeanVerifier


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lean-proof",
        description="Generate Lean proofs with an LLM and verify every attempt with Lean.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    listing = subcommands.add_parser("list-benchmarks", help="list bundled theorem prompts")
    listing.set_defaults(handler=_list_benchmarks)

    text_listing = subcommands.add_parser(
        "list-text-benchmarks", help="list bundled natural-language prompts"
    )
    text_listing.set_defaults(handler=_list_text_benchmarks)

    solve = subcommands.add_parser("solve", help="solve a theorem or benchmark")
    source = solve.add_mutually_exclusive_group(required=True)
    source.add_argument("--benchmark", help="bundled benchmark name")
    source.add_argument("--problem", type=Path, help="path to a theorem-only JSON problem")
    source.add_argument("--theorem", help="inline Lean theorem declaration without ':='")
    solve.add_argument("--name", default="inline", help="name for an inline theorem")
    solve.add_argument("--backend", choices=("openai", "ollama"), default="openai")
    solve.add_argument(
        "--model",
        help="model name (default: OPENAI_MODEL/gpt-5.5 or OLLAMA_MODEL)",
    )
    solve.add_argument("--max-attempts", type=int, default=3)
    solve.add_argument("--artifacts-dir", type=Path, default=Path("runs"))
    solve.add_argument("--project-root", type=Path, default=Path.cwd())
    solve.add_argument("--timeout", type=float, default=120.0)
    solve.set_defaults(handler=_solve)

    solve_text = subcommands.add_parser(
        "solve-text", help="formalize a natural-language proposition and prove it"
    )
    solve_text.add_argument("text", nargs="?", help="natural-language proposition")
    solve_text.add_argument("--benchmark", help="bundled natural-language benchmark")
    solve_text.add_argument("--name", help="simple Lean theorem identifier")
    solve_text.add_argument(
        "--backend", choices=("openai", "ollama"), default="openai"
    )
    solve_text.add_argument(
        "--model",
        help="model name (default: OPENAI_MODEL/gpt-5.5 or OLLAMA_MODEL)",
    )
    solve_text.add_argument("--max-formalization-attempts", type=int, default=3)
    solve_text.add_argument("--max-attempts", type=int, default=3)
    solve_text.add_argument(
        "--artifacts-dir", type=Path, default=Path("autoformalizations")
    )
    solve_text.add_argument("--project-root", type=Path, default=Path.cwd())
    solve_text.add_argument("--timeout", type=float, default=120.0)
    solve_text.set_defaults(handler=_solve_text)

    evaluate = subcommands.add_parser(
        "evaluate", help="run a theorem benchmark suite and aggregate metrics"
    )
    evaluate.add_argument(
        "--benchmark",
        action="append",
        type=Path,
        help="benchmark JSON file or directory; repeatable (default: bundled suite)",
    )
    evaluate.add_argument(
        "--backend",
        choices=("openai", "ollama", "mock"),
        default="openai",
        help="mock is an offline plumbing check using one generic tactic",
    )
    evaluate.add_argument(
        "--model",
        help="model name (ignored by mock; otherwise backend environment/default)",
    )
    evaluate.add_argument("--max-attempts", type=int, default=3)
    evaluate.add_argument("--output-dir", type=Path, default=Path("evaluations"))
    evaluate.add_argument("--project-root", type=Path, default=Path.cwd())
    evaluate.add_argument("--timeout", type=float, default=120.0)
    evaluate.set_defaults(handler=_evaluate)

    evaluate_formalization = subcommands.add_parser(
        "evaluate-formalization",
        help="evaluate natural-language to Lean statement generation",
    )
    evaluate_formalization.add_argument(
        "--benchmark",
        type=Path,
        default=Path("benchmarks/formalization"),
        help="curated formalization benchmark JSON file or directory",
    )
    evaluate_formalization.add_argument(
        "--reviews",
        type=Path,
        help="independent human semantic review JSON from a prior evaluation",
    )
    evaluate_formalization.add_argument(
        "--backend", choices=("openai", "ollama"), default="openai"
    )
    evaluate_formalization.add_argument(
        "--model",
        help="model name (default: OPENAI_MODEL/gpt-5.5 or OLLAMA_MODEL)",
    )
    evaluate_formalization.add_argument(
        "--max-formalization-attempts", type=int, default=3
    )
    evaluate_formalization.add_argument("--max-attempts", type=int, default=3)
    evaluate_formalization.add_argument(
        "--max-equivalence-attempts", type=int, default=2
    )
    evaluate_formalization.add_argument(
        "--output-dir", type=Path, default=Path("formalization_evaluations")
    )
    evaluate_formalization.add_argument("--project-root", type=Path, default=Path.cwd())
    evaluate_formalization.add_argument("--timeout", type=float, default=120.0)
    evaluate_formalization.set_defaults(handler=_evaluate_formalization)

    check_equivalence = subcommands.add_parser(
        "check-equivalence",
        help="Lean-check both implications between two theorem statements",
    )
    check_equivalence.add_argument("reference", type=Path)
    check_equivalence.add_argument("generated", type=Path)
    check_equivalence.add_argument(
        "--backend", choices=("openai", "ollama"), default="openai"
    )
    check_equivalence.add_argument(
        "--model",
        help="model name (default: OPENAI_MODEL/gpt-5.5 or OLLAMA_MODEL)",
    )
    check_equivalence.add_argument("--max-attempts", type=int, default=2)
    check_equivalence.add_argument(
        "--artifacts-dir", type=Path, default=Path("equivalence_checks")
    )
    check_equivalence.add_argument("--project-root", type=Path, default=Path.cwd())
    check_equivalence.add_argument("--timeout", type=float, default=120.0)
    check_equivalence.set_defaults(handler=_check_equivalence)

    compare = subcommands.add_parser(
        "compare", help="compare two saved evaluation.json files"
    )
    compare.add_argument("evaluation_a", type=Path)
    compare.add_argument("evaluation_b", type=Path)
    compare.add_argument("--output-dir", type=Path, default=Path("comparisons"))
    compare.add_argument(
        "--json",
        action="store_true",
        help="also write a machine-readable comparison.json",
    )
    compare.set_defaults(handler=_compare)
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _configure_utf8_stdio() -> None:
    """Keep Lean's Unicode syntax printable on legacy Windows consoles."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _list_benchmarks(_: argparse.Namespace) -> int:
    for problem in list_benchmarks():
        print(f"{problem.name}: {problem.description}")
        print(f"  {problem.theorem}")
    return 0


def _list_text_benchmarks(_: argparse.Namespace) -> int:
    for problem in list_text_benchmarks():
        print(f"{problem.name}: {problem.description}")
        print(f"  {problem.text}")
    return 0


def _solve(args: argparse.Namespace) -> int:
    if args.benchmark:
        problem = load_benchmark(args.benchmark)
    elif args.problem:
        problem = load_problem_file(args.problem)
    else:
        problem = LeanProblem(args.name, args.theorem)

    backend, _ = create_backend(args.backend, args.model)
    verifier = LeanVerifier(args.project_root, timeout_seconds=args.timeout)
    agent = ProofAgent(
        backend,
        verifier,
        max_attempts=args.max_attempts,
        artifacts_root=args.artifacts_dir,
    )
    result = agent.solve(problem)
    status = "SUCCESS" if result.success else "FAILED"
    print(f"{status} after {len(result.attempts)} attempt(s)")
    print(f"Artifacts: {result.run_dir}")
    if result.final_proof:
        print("Proof:")
        print(result.final_proof)
    elif result.attempts:
        print("Final Lean feedback:", file=sys.stderr)
        print(result.attempts[-1].verification.compiler_feedback, file=sys.stderr)
    return 0 if result.success else 1


def _solve_text(args: argparse.Namespace) -> int:
    if bool(args.text) == bool(args.benchmark):
        raise ValueError("provide either natural-language text or --benchmark")
    if args.benchmark:
        bundled = load_text_benchmark(args.benchmark)
        problem = NaturalLanguageProblem(
            args.name or bundled.name,
            bundled.text,
            bundled.description,
            bundled.category,
        )
    else:
        problem = NaturalLanguageProblem(args.name or "autoformalized", args.text)

    backend, _ = create_backend(args.backend, args.model)
    verifier = LeanVerifier(args.project_root, timeout_seconds=args.timeout)
    result = AutoformalizationAgent(
        backend,
        verifier,
        verifier,
        max_formalization_attempts=args.max_formalization_attempts,
        max_proof_attempts=args.max_attempts,
        artifacts_root=args.artifacts_dir,
    ).solve(problem)
    if result.final_theorem:
        print("Formalized theorem:")
        print(result.final_theorem)
    if result.success:
        print("SUCCESS: the generated theorem and proof were accepted by Lean")
        print("Verified proof:")
        print(result.verified_proof)
    elif result.final_problem is None:
        print("FAILED: no valid theorem statement was produced", file=sys.stderr)
    else:
        print("FAILED: theorem was valid but proof attempts were exhausted", file=sys.stderr)
    print(f"Artifacts: {result.run_dir}")
    return 0 if result.success else 1


def _evaluate(args: argparse.Namespace) -> int:
    problems = (
        load_benchmark_paths(args.benchmark)
        if args.benchmark
        else list_benchmarks()
    )
    if args.backend == "mock":
        backend = OfflineMockBackend()
        model = None
    else:
        backend, model = create_backend(args.backend, args.model)
    verifier = LeanVerifier(args.project_root, timeout_seconds=args.timeout)
    result = EvaluationRunner(
        backend,
        verifier,
        max_attempts=args.max_attempts,
        output_root=args.output_dir,
        backend_name=args.backend,
        model=model,
    ).run(problems)
    print(render_markdown(result), end="")
    print(f"JSON: {result.evaluation_dir / 'evaluation.json'}")
    print(f"Markdown: {result.evaluation_dir / 'summary.md'}")
    return 0


def _check_equivalence(args: argparse.Namespace) -> int:
    reference = load_statement_file(args.reference)
    generated = load_statement_file(args.generated)
    imports = merge_imports(reference.imports, generated.imports)
    verifier = LeanVerifier(args.project_root, timeout_seconds=args.timeout)
    backend, _ = create_backend(args.backend, args.model)
    result = SemanticEquivalenceChecker(
        backend,
        verifier,
        max_attempts=args.max_attempts,
        artifacts_root=args.artifacts_dir,
    ).check(reference.statement, generated.statement, imports=imports)
    print(render_equivalence(result), end="")
    return 0


def _evaluate_formalization(args: argparse.Namespace) -> int:
    problems = load_formalization_benchmarks(args.benchmark)
    reviews = load_semantic_reviews(args.reviews) if args.reviews else None
    verifier = LeanVerifier(args.project_root, timeout_seconds=args.timeout)
    backend, model = create_backend(args.backend, args.model)
    result = FormalizationEvaluationRunner(
        backend,
        verifier,
        verifier,
        max_formalization_attempts=args.max_formalization_attempts,
        max_proof_attempts=args.max_attempts,
        max_equivalence_attempts=args.max_equivalence_attempts,
        output_root=args.output_dir,
        backend_name=args.backend,
        model=model,
        reviews=reviews,
    ).run(problems)
    print(render_formalization_markdown(result), end="")
    print(f"JSON: {result.evaluation_dir / 'evaluation.json'}")
    print(f"Markdown: {result.evaluation_dir / 'summary.md'}")
    print(f"Semantic review file: {result.evaluation_dir / 'semantic_reviews.json'}")
    return 0


def _compare(args: argparse.Namespace) -> int:
    result = compare_evaluations(args.evaluation_a, args.evaluation_b)
    markdown_path, json_path = write_comparison(
        result, args.output_dir, write_json=args.json
    )
    print(render_terminal(result), end="")
    print(f"Markdown: {markdown_path}")
    if json_path:
        print(f"JSON: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
