"""Deterministic lexical retrieval over declarations in the local Lean environment."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Protocol

from .models import LeanProblem


_MARKER = "__LEAN_PROOF_AGENT_PREMISE__"
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_']*")
_QUALIFIED_RE = re.compile(
    r"[A-Z][A-Za-z0-9_']*(?:\.[A-Za-z_][A-Za-z0-9_']*)+"
)
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_STOP_WORDS = frozenset(
    {
        "theorem",
        "example",
        "type",
        "prop",
        "true",
        "false",
        "this",
        "that",
        "with",
        "from",
        "have",
        "show",
    }
)
_SYMBOL_WORDS = {
    "ℕ": ("nat", "natural"),
    "ℤ": ("int", "integer"),
    "ℝ": ("real",),
    "∧": ("and",),
    "∨": ("or",),
    "↔": ("iff",),
    "≤": ("le",),
    "<": ("lt",),
    "≥": ("ge",),
    "∈": ("mem",),
    "∉": ("not_mem",),
    "⊆": ("subset",),
    "∪": ("union",),
    "∩": ("inter",),
    "⁻¹": ("inv", "inverse"),
    "∘": ("comp", "compose"),
}
_SEARCH_GENERIC = frozenset(
    {
        "algebra",
        "arith",
        "func",
        "function",
        "ineq",
        "int",
        "integer",
        "logic",
        "nat",
        "natural",
        "real",
        "set",
        "sets",
    }
)
_WORD_ALIASES = {
    "membership": "mem",
    "nonnegative": "nonneg",
    "implication": "imp",
}


@dataclass(frozen=True, slots=True)
class Premise:
    """One verified declaration candidate returned by lexical retrieval."""

    name: str
    signature: str
    module: str
    score: float


class PremiseRetriever(Protocol):
    def retrieve(self, problem: LeanProblem, *, top_k: int) -> tuple[Premise, ...]:
        """Return at most ``top_k`` deterministic declaration candidates."""


class MathlibRetriever:
    """Query imported declarations by lexical overlap with the current theorem.

    Lean itself enumerates and pretty-prints proposition-valued declarations, so
    every returned name exists in the exact local environment used for checking.
    No benchmark statements, answer map, vector index, or remote service is used.
    """

    def __init__(
        self,
        project_root: Path,
        *,
        lake_executable: str | Path | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.project_root = project_root.resolve()
        self.lake_executable = str(lake_executable or _find_lake())
        self.timeout_seconds = timeout_seconds
        self._cache: dict[
            tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]],
            tuple[Premise, ...],
        ] = {}

    def retrieve(self, problem: LeanProblem, *, top_k: int) -> tuple[Premise, ...]:
        if top_k < 1:
            raise ValueError("premise_top_k must be at least 1")
        tokens = _query_tokens(problem.theorem)
        search_tokens = _search_tokens(problem.theorem, tokens)
        key = (problem.imports, search_tokens, tokens)
        candidates = self._cache.get(key)
        if candidates is None:
            candidates = self._query_environment(
                problem.imports, tokens, search_tokens
            )
            self._cache[key] = candidates
        return candidates[:top_k]

    def _query_environment(
        self,
        imports: tuple[str, ...],
        tokens: tuple[str, ...],
        search_tokens: tuple[str, ...],
    ) -> tuple[Premise, ...]:
        source = _lean_query_source(imports, search_tokens)
        with tempfile.TemporaryDirectory(prefix="lean-premises-") as directory:
            path = Path(directory) / "Query.lean"
            path.write_text(source, encoding="utf-8")
            try:
                completed = subprocess.run(
                    [self.lake_executable, "env", "lean", str(path)],
                    cwd=self.project_root,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("Mathlib premise retrieval timed out") from exc
        if completed.returncode != 0:
            feedback = "\n".join(
                part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
            )
            raise RuntimeError(f"Mathlib premise retrieval failed:\n{feedback}")

        unique: dict[str, Premise] = {}
        for line in completed.stdout.splitlines():
            marker = line.find(_MARKER)
            if marker < 0:
                continue
            fields = line[marker + len(_MARKER) :].lstrip("\t").split("\t", 2)
            if len(fields) != 3:
                continue
            name, module, signature = fields
            score = _score(name, signature, tokens)
            if score > 0 and name not in unique:
                unique[name] = Premise(name, signature, module, score)
        return tuple(
            sorted(unique.values(), key=lambda item: (-item.score, item.name, item.module))
        )


def write_premises(path: Path, premises: tuple[Premise, ...]) -> None:
    path.write_text(
        json.dumps([asdict(item) for item in premises], ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


def _query_tokens(theorem: str) -> tuple[str, ...]:
    declaration = re.sub(r"^\s*(?:theorem|example)\s+", "", theorem, count=1)
    words: set[str] = set()
    words.update(item.lower().replace("'", "") for item in _QUALIFIED_RE.findall(declaration))
    for identifier in _WORD_RE.findall(declaration):
        for dotted in identifier.replace("'", "").split("_"):
            for part in _CAMEL_RE.sub(" ", dotted).split():
                lowered = part.lower()
                if len(lowered) >= 2 and lowered not in _STOP_WORDS:
                    words.add(lowered)
    for symbol, aliases in _SYMBOL_WORDS.items():
        if symbol in declaration:
            words.update(aliases)
    return tuple(sorted(words))


def _search_tokens(theorem: str, scoring_tokens: tuple[str, ...]) -> tuple[str, ...]:
    match = re.match(
        r"^\s*(?:theorem|example)\s+([A-Za-z_][A-Za-z0-9_']*)", theorem
    )
    name_parts = [] if match is None else match.group(1).lower().split("_")
    compounds = {
        f"{left}_{right}"
        for left, right in zip(name_parts, name_parts[1:])
        if left not in _SEARCH_GENERIC or right not in _SEARCH_GENERIC
    }
    for index, word in enumerate(name_parts):
        alias = _WORD_ALIASES.get(word)
        if alias:
            compounds.add(alias)
            if index > 0:
                compounds.add(f"{name_parts[index - 1]}_{alias}")
                compounds.add(f"{alias}_{name_parts[index - 1]}")
            if index + 1 < len(name_parts):
                compounds.add(f"{alias}_{name_parts[index + 1]}")
                compounds.add(f"{name_parts[index + 1]}_{alias}")
    qualified = {token for token in scoring_tokens if "." in token}
    distinctive_candidates = {
        _WORD_ALIASES.get(token, token)
        for token in scoring_tokens
        if token not in _SEARCH_GENERIC and len(token) >= 5
    }
    distinctive = (
        {max(distinctive_candidates, key=lambda item: (len(item), item))}
        if distinctive_candidates
        else set()
    )
    selected = compounds | qualified | distinctive
    if not selected:
        selected = {
            token
            for token in scoring_tokens
            if token not in _SEARCH_GENERIC and len(token) >= 3
        }
    return tuple(sorted(selected))


def _score(name: str, signature: str, tokens: tuple[str, ...]) -> float:
    lowered_name = name.lower()
    name_parts = {
        part
        for item in re.split(r"[._]", name)
        for part in _CAMEL_RE.sub(" ", item).lower().split()
        if part
    }
    lowered_signature = signature.lower()
    score = 0.0
    for token in tokens:
        if "." in token and token in lowered_name:
            score += 12.0
        if token in name_parts:
            score += 8.0
        elif token in lowered_name:
            score += 4.0
        if re.search(rf"(?<![a-z0-9_']){re.escape(token)}(?![a-z0-9_'])", lowered_signature):
            score += 1.0
    if lowered_name.startswith(("mathlib.", "lean.", "_private")):
        score -= 2.0
    score -= min(len(signature), 1_000) * 0.001
    score -= len(name) * 0.01
    return score


def _lean_query_source(imports: tuple[str, ...], tokens: tuple[str, ...]) -> str:
    import_text = "\n".join(f"import {item}" for item in imports)
    lean_tokens = ", ".join(json.dumps(token) for token in tokens)
    return f'''{import_text}

open Lean Meta

run_cmd Lean.Elab.Command.liftTermElabM do
  let queryTokens : Array String := #[{lean_tokens}]
  let env ← getEnv
  for (name, info) in env.constants.map₁ do
    let nameText := name.toString
    let lowered := nameText.toLower
    if !nameText.startsWith "_private" && !nameText.contains "._proof_" && queryTokens.any (fun token => lowered.contains token) then
      if ← isProp info.type then
        let rendered ← ppExpr info.type
        let signature := (rendered.pretty.replace "\\n" " ").replace "\\t" " "
        let moduleName := (env.getModuleFor? name).map (·.toString) |>.getD "unknown"
        logInfo m!"{_MARKER}\\t{{nameText}}\\t{{moduleName}}\\t{{signature}}"
'''


def _find_lake() -> Path:
    found = shutil.which("lake")
    if found:
        return Path(found)
    windows_default = Path.home() / ".elan" / "bin" / "lake.exe"
    if windows_default.is_file():
        return windows_default
    raise RuntimeError("lake executable was not found")
