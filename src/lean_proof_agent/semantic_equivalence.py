"""Conservative, Lean-verified semantic equivalence checking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid

from .agent import ProofAgent, ProofVerifier
from .llm import LLMBackend
from .models import LeanProblem, RunResult


DIRECTION_STATUSES = frozenset({"verified", "failed", "unknown"})
EQUIVALENCE_RESULTS = frozenset({"equivalent", "not_equivalent", "unknown"})
_DECLARATION_RE = re.compile(
    r"^\s*(?:theorem|example)\s+([A-Za-z_][A-Za-z0-9_']*)\b", re.DOTALL
)


@dataclass(frozen=True, slots=True)
class EquivalenceDirectionResult:
    """Kernel-checking outcome for one implication direction."""

    direction: str
    status: str
    theorem: str
    proof_result: RunResult | None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.direction not in {"forward", "backward"}:
            raise ValueError(f"invalid equivalence direction: {self.direction}")
        if self.status not in DIRECTION_STATUSES:
            raise ValueError(f"invalid equivalence direction status: {self.status}")


@dataclass(frozen=True, slots=True)
class SemanticEquivalenceResult:
    """Two implication checks and their conservative combined result."""

    reference_statement: str
    generated_statement: str
    imports: tuple[str, ...]
    forward: EquivalenceDirectionResult
    backward: EquivalenceDirectionResult
    result: str
    run_dir: Path

    def __post_init__(self) -> None:
        if self.result not in EQUIVALENCE_RESULTS:
            raise ValueError(f"invalid semantic equivalence result: {self.result}")


@dataclass(frozen=True, slots=True)
class StatementFile:
    """Statement and imports loaded by the standalone CLI."""

    statement: str
    imports: tuple[str, ...]


class SemanticEquivalenceChecker:
    """Prove reference→generated and generated→reference independently."""

    def __init__(
        self,
        backend: LLMBackend,
        verifier: ProofVerifier,
        *,
        max_attempts: int = 2,
        artifacts_root: Path = Path("equivalence_checks"),
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.backend = backend
        self.verifier = verifier
        self.max_attempts = max_attempts
        self.artifacts_root = artifacts_root

    def check(
        self,
        reference_statement: str,
        generated_statement: str,
        *,
        imports: tuple[str, ...] = ("Mathlib",),
    ) -> SemanticEquivalenceResult:
        """Check both implications; never infer inequivalence from failed search."""

        if not imports:
            raise ValueError("at least one Lean import is required")
        reference = theorem_to_proposition(reference_statement)
        generated = theorem_to_proposition(generated_statement)
        run_dir = _create_run_dir(self.artifacts_root)
        _write_json(
            run_dir / "input.json",
            {
                "reference_statement": reference_statement,
                "generated_statement": generated_statement,
                "reference_proposition": reference,
                "generated_proposition": generated,
                "imports": list(imports),
                "max_attempts": self.max_attempts,
            },
        )
        forward = self._check_direction(
            "forward", reference, generated, imports, run_dir
        )
        backward = self._check_direction(
            "backward", generated, reference, imports, run_dir
        )
        combined = (
            "equivalent"
            if forward.status == "verified" and backward.status == "verified"
            else "unknown"
        )
        result = SemanticEquivalenceResult(
            reference_statement,
            generated_statement,
            imports,
            forward,
            backward,
            combined,
            run_dir,
        )
        _write_summary(result)
        return result

    def _check_direction(
        self,
        direction: str,
        premise: str,
        conclusion: str,
        imports: tuple[str, ...],
        run_dir: Path,
    ) -> EquivalenceDirectionResult:
        name = f"semantic_equivalence_{direction}"
        theorem = f"theorem {name} : ({premise}) → ({conclusion})"
        problem = LeanProblem(
            name,
            theorem,
            imports,
            description=f"Semantic equivalence {direction} implication",
            category="semantic-equivalence",
        )
        try:
            proof_result = ProofAgent(
                self.backend,
                self.verifier,
                max_attempts=self.max_attempts,
                artifacts_root=run_dir / direction,
            ).solve(problem)
        except Exception as exc:
            return EquivalenceDirectionResult(
                direction,
                "failed",
                theorem,
                None,
                f"{type(exc).__name__}: {exc}",
            )
        status = "verified" if proof_result.success else "unknown"
        error = None
        if not proof_result.success and proof_result.attempts:
            error = proof_result.attempts[-1].verification.compiler_feedback
        return EquivalenceDirectionResult(
            direction, status, theorem, proof_result, error
        )


def theorem_to_proposition(statement: str) -> str:
    """Turn one theorem declaration into a closed proposition expression."""

    match = _DECLARATION_RE.match(statement)
    if not match:
        raise ValueError("statement must start with one theorem or example declaration")
    remainder = statement[match.end() :].strip()
    colon = _find_top_level_colon(remainder)
    if colon is None:
        raise ValueError("theorem declaration is missing its result colon")
    binders = remainder[:colon].strip()
    conclusion = remainder[colon + 1 :].strip()
    if not conclusion:
        raise ValueError("theorem declaration has an empty proposition")
    if ":=" in conclusion:
        raise ValueError("theorem declaration must not contain a proof body")
    return conclusion if not binders else f"∀ {binders}, {conclusion}"


def load_statement_file(path: Path) -> StatementFile:
    """Load a statement JSON accepted by ``check-equivalence``."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("statement file must contain one JSON object")
    statement = next(
        (
            payload[key]
            for key in (
                "statement",
                "theorem",
                "reference_statement",
                "generated_statement",
                "final_theorem",
            )
            if isinstance(payload.get(key), str)
        ),
        None,
    )
    if not isinstance(statement, str):
        raise ValueError(
            "statement file requires statement, theorem, reference_statement, "
            "generated_statement, or final_theorem"
        )
    imports_value = payload.get("imports", ["Mathlib"])
    if not isinstance(imports_value, list) or not all(
        isinstance(item, str) for item in imports_value
    ):
        raise ValueError("statement imports must be a list of strings")
    theorem_to_proposition(statement)
    return StatementFile(statement, tuple(imports_value))


def merge_imports(*groups: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item for group in groups for item in group))


def render_equivalence(result: SemanticEquivalenceResult) -> str:
    """Render a concise terminal/Markdown-compatible summary."""

    return "\n".join(
        [
            "Semantic Equivalence",
            f"Forward (reference → generated): {result.forward.status}",
            f"Backward (generated → reference): {result.backward.status}",
            f"Result: {result.result}",
            f"Artifacts: {result.run_dir}",
            "",
        ]
    )


def _find_top_level_colon(text: str) -> int | None:
    stack: list[str] = []
    closing = {"(": ")", "{": "}", "[": "]"}
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in closing:
            stack.append(closing[char])
        elif stack and char == stack[-1]:
            stack.pop()
        elif char == ":" and not stack:
            return index
    if stack or in_string:
        raise ValueError("unbalanced theorem binder syntax")
    return None


def _create_run_dir(root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = root.resolve() / f"{stamp}-equivalence-{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def _write_summary(result: SemanticEquivalenceResult) -> None:
    def direction_payload(direction: EquivalenceDirectionResult) -> dict[str, object]:
        proof = direction.proof_result
        return {
            "status": direction.status,
            "theorem": direction.theorem,
            "error": direction.error,
            "proof_run_dir": str(proof.run_dir) if proof else None,
            "proof_attempts": len(proof.attempts) if proof else 0,
            "verified_proof": proof.final_proof if proof else None,
        }

    _write_json(
        result.run_dir / "summary.json",
        {
            "result": result.result,
            "forward": direction_payload(result.forward),
            "backward": direction_payload(result.backward),
            "not_equivalent_evidence": None,
            "note": (
                "Proof-search failure is unknown, never evidence of inequivalence."
            ),
        },
    )


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
