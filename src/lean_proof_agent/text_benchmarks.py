"""Load bundled natural-language autoformalization benchmarks."""

from __future__ import annotations

import json
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

from .formalization import NaturalLanguageProblem


def _benchmark_dir() -> Traversable:
    packaged = files("lean_proof_agent").joinpath("text_benchmarks")
    if packaged.is_dir():
        return packaged
    return Path(__file__).resolve().parents[2] / "text_benchmarks"


def list_text_benchmarks() -> tuple[NaturalLanguageProblem, ...]:
    problems = []
    for item in sorted(_benchmark_dir().iterdir(), key=lambda value: value.name):
        if item.name.endswith(".json"):
            problems.append(_from_dict(json.loads(item.read_text(encoding="utf-8"))))
    return tuple(problems)


def load_text_benchmark(name: str) -> NaturalLanguageProblem:
    for problem in list_text_benchmarks():
        if problem.name == name:
            return problem
    choices = ", ".join(item.name for item in list_text_benchmarks())
    raise KeyError(f"unknown text benchmark {name!r}; available: {choices}")


def _from_dict(data: dict[str, object]) -> NaturalLanguageProblem:
    name = data.get("name")
    text = data.get("text")
    description = data.get("description", "")
    category = data.get("category", "uncategorized")
    if not isinstance(name, str) or not isinstance(text, str):
        raise ValueError("text benchmark requires string fields 'name' and 'text'")
    if not isinstance(description, str) or not isinstance(category, str):
        raise ValueError("text benchmark description and category must be strings")
    return NaturalLanguageProblem(name, text, description, category)
