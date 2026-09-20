"""Command-line interface."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from .agent import ProofAgent
from .benchmarks import list_benchmarks, load_benchmark, load_problem_file
from .models import LeanProblem
from .openai_backend import OpenAIBackend
from .verifier import LeanVerifier


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lean-proof",
        description="Generate Lean proofs with an LLM and verify every attempt with Lean.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    listing = subcommands.add_parser("list-benchmarks", help="list bundled theorem prompts")
    listing.set_defaults(handler=_list_benchmarks)

    solve = subcommands.add_parser("solve", help="solve a theorem or benchmark")
    source = solve.add_mutually_exclusive_group(required=True)
    source.add_argument("--benchmark", help="bundled benchmark name")
    source.add_argument("--problem", type=Path, help="path to a theorem-only JSON problem")
    source.add_argument("--theorem", help="inline Lean theorem declaration without ':='")
    solve.add_argument("--name", default="inline", help="name for an inline theorem")
    solve.add_argument(
        "--model",
        default=os.environ.get("OPENAI_MODEL", "gpt-5.5"),
        help="OpenAI model (default: OPENAI_MODEL or gpt-5.5)",
    )
    solve.add_argument("--max-attempts", type=int, default=3)
    solve.add_argument("--artifacts-dir", type=Path, default=Path("runs"))
    solve.add_argument("--project-root", type=Path, default=Path.cwd())
    solve.add_argument("--timeout", type=float, default=120.0)
    solve.set_defaults(handler=_solve)
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


def _solve(args: argparse.Namespace) -> int:
    if args.benchmark:
        problem = load_benchmark(args.benchmark)
    elif args.problem:
        problem = load_problem_file(args.problem)
    else:
        problem = LeanProblem(args.name, args.theorem)

    backend = OpenAIBackend(args.model)
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


if __name__ == "__main__":
    raise SystemExit(main())
