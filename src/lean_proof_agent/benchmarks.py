"""Load theorem-only benchmark definitions (never stored solutions)."""

from __future__ import annotations

import json
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

from .models import LeanProblem


def _benchmark_dir() -> Traversable:
    packaged = files("lean_proof_agent").joinpath("benchmarks")
    if packaged.is_dir():
        return packaged
    return Path(__file__).resolve().parents[2] / "benchmarks"


def list_benchmarks() -> tuple[LeanProblem, ...]:
    problems: list[LeanProblem] = []
    root = _benchmark_dir()
    for item in sorted(root.iterdir(), key=lambda value: value.name):
        if item.name.endswith(".json"):
            data = json.loads(item.read_text(encoding="utf-8"))
            problems.append(_from_dict(data))
    return tuple(problems)


def load_benchmark(name: str) -> LeanProblem:
    for problem in list_benchmarks():
        if problem.name == name:
            return problem
    choices = ", ".join(item.name for item in list_benchmarks())
    raise KeyError(f"unknown benchmark {name!r}; available: {choices}")


def load_problem_file(path: Path) -> LeanProblem:
    data = json.loads(path.read_text(encoding="utf-8"))
    return _from_dict(data)


def _from_dict(data: dict[str, object]) -> LeanProblem:
    imports = data.get("imports", ["Mathlib"])
    if not isinstance(imports, list) or not all(isinstance(x, str) for x in imports):
        raise ValueError("problem imports must be a list of strings")
    name = data.get("name")
    theorem = data.get("theorem")
    description = data.get("description", "")
    if not isinstance(name, str) or not isinstance(theorem, str):
        raise ValueError("problem requires string fields 'name' and 'theorem'")
    if not isinstance(description, str):
        raise ValueError("problem description must be a string")
    return LeanProblem(name, theorem, tuple(imports), description)
