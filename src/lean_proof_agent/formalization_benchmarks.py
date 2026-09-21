"""Curated natural-language/Lean statement benchmark definitions."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

from .formalization import NaturalLanguageProblem, normalize_theorem_statement
from .models import LeanProblem


_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_']*$")


@dataclass(frozen=True, slots=True)
class FormalizationBenchmark:
    """One human-reviewed natural-language/reference-statement pair."""

    id: str
    natural_language: str
    reference_statement: str
    imports: tuple[str, ...]
    category: str
    assumptions: tuple[str, ...]
    ambiguity_notes: str

    def __post_init__(self) -> None:
        if not _ID_RE.fullmatch(self.id):
            raise ValueError("benchmark id must be a simple Lean identifier")
        if not self.natural_language.strip():
            raise ValueError("benchmark natural_language must not be empty")
        if not self.category.strip():
            raise ValueError("benchmark category must not be empty")
        statement = normalize_theorem_statement(
            self.reference_statement, expected_name=self.id
        )
        LeanProblem(self.id, statement, self.imports, self.natural_language, self.category)

    def natural_language_problem(self) -> NaturalLanguageProblem:
        return NaturalLanguageProblem(
            self.id,
            self.natural_language,
            description=self.natural_language,
            category=self.category,
        )


def load_formalization_benchmarks(path: Path) -> tuple[FormalizationBenchmark, ...]:
    """Load one JSON benchmark file or all JSON files directly in a directory."""

    resolved = path.resolve()
    if resolved.is_file():
        problems = _load_file(resolved)
    elif resolved.is_dir():
        problems = tuple(
            problem
            for item in sorted(resolved.glob("*.json"))
            for problem in _load_file(item)
        )
    else:
        raise FileNotFoundError(f"formalization benchmark path does not exist: {path}")
    if not problems:
        raise ValueError("formalization benchmark requires at least one problem")
    ids = [problem.id for problem in problems]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        raise ValueError(f"duplicate formalization benchmark id(s): {', '.join(duplicates)}")
    return problems


def _load_file(path: Path) -> tuple[FormalizationBenchmark, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else [payload]
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"benchmark must contain an object or array of objects: {path}")
    return tuple(_from_dict(row) for row in rows)


def _from_dict(data: dict[str, object]) -> FormalizationBenchmark:
    required = (
        "id",
        "natural_language",
        "reference_statement",
        "imports",
        "category",
        "assumptions",
        "ambiguity_notes",
    )
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"formalization benchmark missing field(s): {', '.join(missing)}")
    scalar_fields = (
        "id",
        "natural_language",
        "reference_statement",
        "category",
        "ambiguity_notes",
    )
    if not all(isinstance(data[key], str) for key in scalar_fields):
        raise ValueError("formalization benchmark scalar fields must be strings")
    imports = data["imports"]
    assumptions = data["assumptions"]
    if not isinstance(imports, list) or not all(isinstance(x, str) for x in imports):
        raise ValueError("formalization benchmark imports must be a list of strings")
    if not isinstance(assumptions, list) or not all(
        isinstance(x, str) for x in assumptions
    ):
        raise ValueError("formalization benchmark assumptions must be a list of strings")
    return FormalizationBenchmark(
        id=str(data["id"]),
        natural_language=str(data["natural_language"]),
        reference_statement=str(data["reference_statement"]),
        imports=tuple(imports),
        category=str(data["category"]),
        assumptions=tuple(assumptions),
        ambiguity_notes=str(data["ambiguity_notes"]),
    )
