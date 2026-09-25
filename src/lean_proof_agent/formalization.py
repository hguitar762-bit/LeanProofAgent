"""Natural-language to Lean statement generation with compiler-guided repair."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import time
from typing import Protocol

from .agent import ProofAgent, ProofGenerationError, ProofVerifier
from .artifacts import create_run_dir
from .llm import LLMBackend
from .models import (
    GenerationResult,
    LeanProblem,
    RunResult,
    TokenUsage,
    VerificationResult,
    reject_unsafe_lean,
)


FORMALIZATION_SYSTEM_PROMPT = """You translate natural-language mathematics into Lean 4 theorem statements using Mathlib.
Return exactly one complete `theorem` declaration with a name, parameters, types, and conclusion.
Return the declaration only: no proof body, `:=`, `by`, `sorry`, `admit`, `axiom`, imports, Markdown, or prose.
Preserve the user's intended meaning as carefully as possible, but do not claim that formalization establishes semantic equivalence."""

_FENCE_RE = re.compile(r"^```(?:lean)?\s*\n?(.*?)\n?```$", re.DOTALL | re.IGNORECASE)
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_']*$")
_THEOREM_RE = re.compile(r"^\s*theorem\s+([A-Za-z_][A-Za-z0-9_']*)\b", re.DOTALL)
_EXTRA_COMMAND_RE = re.compile(
    r"(?m)^\s*(?:"
    r"import|open|namespace|section|end|set_option|run_cmd|"
    r"theorem|lemma|example|axiom|def|opaque|abbrev|instance|"
    r"structure|class|inductive|macro|syntax|elab"
    r")\b"
)


class StatementVerifier(Protocol):
    """Lean compiler interface used to elaborate generated statements."""

    def verify(self, source_path: Path) -> VerificationResult:
        """Check one temporary statement-validation source file."""


@dataclass(frozen=True, slots=True)
class NaturalLanguageProblem:
    """A named natural-language proposition awaiting formalization."""

    name: str
    text: str
    description: str = ""
    category: str = "uncategorized"

    def __post_init__(self) -> None:
        if not _NAME_RE.fullmatch(self.name):
            raise ValueError("problem name must be a simple Lean identifier")
        if not self.text.strip():
            raise ValueError("natural-language problem must not be empty")
        if not self.category.strip():
            raise ValueError("problem category must not be empty")


@dataclass(frozen=True, slots=True)
class FormalizationAttempt:
    """One generated theorem statement and its Lean elaboration result."""

    number: int
    raw_response: str
    theorem_statement: str | None
    source_path: Path
    verification: VerificationResult
    generation_seconds: float = 0.0
    token_usage: TokenUsage | None = None
    finish_reason: str | None = None


@dataclass(frozen=True, slots=True)
class AutoformalizationResult:
    """Final formalization and the existing proof-agent result, when reached."""

    natural_language_problem: NaturalLanguageProblem
    formalization_attempts: tuple[FormalizationAttempt, ...]
    final_problem: LeanProblem | None
    proof_result: RunResult | None
    run_dir: Path

    @property
    def success(self) -> bool:
        return self.proof_result is not None and self.proof_result.success

    @property
    def final_theorem(self) -> str | None:
        return self.final_problem.theorem if self.final_problem else None

    @property
    def verified_proof(self) -> str | None:
        return self.proof_result.final_proof if self.proof_result else None


class AutoformalizationGenerationError(RuntimeError):
    """Backend failure carrying all autoformalization work completed so far."""

    def __init__(
        self, cause: Exception, partial_result: AutoformalizationResult
    ) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.partial_result = partial_result


class AutoformalizationAgent:
    """Generate a theorem statement, elaborate it, then invoke ``ProofAgent``."""

    def __init__(
        self,
        backend: LLMBackend,
        statement_verifier: StatementVerifier,
        proof_verifier: ProofVerifier,
        *,
        max_formalization_attempts: int = 3,
        max_proof_attempts: int = 3,
        artifacts_root: Path = Path("autoformalizations"),
        imports: tuple[str, ...] = ("Mathlib",),
    ) -> None:
        if max_formalization_attempts < 1:
            raise ValueError("max_formalization_attempts must be at least 1")
        if max_proof_attempts < 1:
            raise ValueError("max_proof_attempts must be at least 1")
        self.backend = backend
        self.statement_verifier = statement_verifier
        self.proof_verifier = proof_verifier
        self.max_formalization_attempts = max_formalization_attempts
        self.max_proof_attempts = max_proof_attempts
        self.artifacts_root = artifacts_root
        self.imports = imports

    def solve(self, problem: NaturalLanguageProblem) -> AutoformalizationResult:
        run_dir = create_run_dir(self.artifacts_root, problem.name)
        _write_input(
            run_dir,
            problem,
            self.imports,
            self.max_formalization_attempts,
            self.max_proof_attempts,
        )
        attempts: list[FormalizationAttempt] = []
        previous_statement: str | None = None
        lean_error: str | None = None
        final_problem: LeanProblem | None = None

        for number in range(1, self.max_formalization_attempts + 1):
            prompt = build_formalization_prompt(
                problem,
                self.imports,
                attempt_number=number,
                previous_statement=previous_statement,
                lean_error=lean_error,
            )
            started = time.monotonic()
            try:
                generated = self.backend.generate(
                    system_prompt=FORMALIZATION_SYSTEM_PROMPT,
                    user_prompt=prompt,
                )
            except Exception as exc:
                partial_result = AutoformalizationResult(
                    problem, tuple(attempts), None, None, run_dir
                )
                _write_autoformalization_summary(partial_result)
                raise AutoformalizationGenerationError(
                    exc, partial_result
                ) from exc
            generation_seconds = time.monotonic() - started
            raw_response, token_usage, finish_reason = _generated_text(generated)
            source_path = run_dir / f"formalization_{number:02d}.lean"
            candidate: LeanProblem | None = None

            try:
                statement = normalize_theorem_statement(
                    raw_response, expected_name=problem.name
                )
                candidate = LeanProblem(
                    problem.name,
                    statement,
                    self.imports,
                    problem.description or problem.text,
                    problem.category,
                )
            except ValueError as exc:
                statement = None
                source_path.write_text(
                    f"/- Rejected before Lean invocation: {exc} -/\n",
                    encoding="utf-8",
                )
                verification = VerificationResult(
                    success=False,
                    command=(),
                    exit_code=None,
                    stdout="",
                    stderr=f"Safety/format rejection: {exc}",
                    duration_seconds=0.0,
                )
            else:
                source_path.write_text(
                    _statement_validation_source(candidate), encoding="utf-8"
                )
                verification = self.statement_verifier.verify(source_path)

            attempt = FormalizationAttempt(
                number=number,
                raw_response=raw_response,
                theorem_statement=statement,
                source_path=source_path,
                verification=verification,
                generation_seconds=generation_seconds,
                token_usage=token_usage,
                finish_reason=finish_reason,
            )
            attempts.append(attempt)
            _write_formalization_attempt(run_dir, attempt)
            if verification.success:
                if candidate is None:
                    raise RuntimeError("statement validation succeeded without a candidate")
                final_problem = candidate
                break
            previous_statement = statement or raw_response.strip()
            lean_error = verification.compiler_feedback

        if final_problem is None:
            result = AutoformalizationResult(
                problem, tuple(attempts), None, None, run_dir
            )
            _write_autoformalization_summary(result)
            return result

        try:
            proof_result = ProofAgent(
                self.backend,
                self.proof_verifier,
                max_attempts=self.max_proof_attempts,
                artifacts_root=run_dir / "proof",
            ).solve(final_problem)
        except ProofGenerationError as exc:
            partial_result = AutoformalizationResult(
                problem,
                tuple(attempts),
                final_problem,
                exc.partial_result,
                run_dir,
            )
            _write_autoformalization_summary(partial_result)
            raise AutoformalizationGenerationError(
                exc.cause, partial_result
            ) from exc
        result = AutoformalizationResult(
            problem, tuple(attempts), final_problem, proof_result, run_dir
        )
        _write_autoformalization_summary(result)
        return result


def normalize_theorem_statement(
    response: str, *, expected_name: str | None = None
) -> str:
    """Normalize one declaration and enforce the statement-only boundary."""

    text = response.strip()
    match = _FENCE_RE.fullmatch(text)
    if match:
        text = match.group(1).strip()
    if not text:
        raise ValueError("LLM returned an empty formalization")
    if "```" in text:
        raise ValueError("LLM response contains an unmatched or extra code fence")
    declaration = _THEOREM_RE.match(text)
    if not declaration:
        raise ValueError("formalization must be exactly one theorem declaration")
    if expected_name is not None and declaration.group(1) != expected_name:
        raise ValueError(f"formalization theorem must be named {expected_name!r}")
    remainder = text[declaration.end() :]
    if "#" in remainder or _EXTRA_COMMAND_RE.search(remainder):
        raise ValueError("formalization must not contain extra Lean commands")
    if ":=" in text:
        raise ValueError("formalization must not contain a proof body")
    if re.search(r"\bwhere\b", text):
        raise ValueError("formalization must not contain a where block")
    reject_unsafe_lean(text, label="generated formalization")
    return text


def build_formalization_prompt(
    problem: NaturalLanguageProblem,
    imports: tuple[str, ...],
    *,
    attempt_number: int,
    previous_statement: str | None = None,
    lean_error: str | None = None,
    max_feedback_chars: int = 12_000,
) -> str:
    """Build the initial or Lean-feedback-guided statement prompt."""

    available_imports = ", ".join(imports)
    base = (
        f"Attempt {attempt_number}. Formalize the proposition below as Lean 4.\n"
        f"Required theorem name: {problem.name}\n"
        f"Available imports: {available_imports}\n\n"
        f"Natural-language proposition:\n{problem.text.strip()}"
    )
    if previous_statement is None or lean_error is None:
        return base
    return (
        f"{base}\n\n"
        "The previous theorem statement was rejected. Repair only the statement "
        "using the exact Lean feedback below.\n\n"
        f"Previous statement:\n{previous_statement}\n\n"
        f"Lean feedback:\n{lean_error[-max_feedback_chars:]}"
    )


def _statement_validation_source(problem: LeanProblem) -> str:
    imports = "\n".join(f"import {item}" for item in problem.imports)
    declaration = re.sub(r"^\s*theorem\b", "axiom", problem.theorem, count=1)
    return (
        f"{imports}\n\n"
        "set_option autoImplicit false\n\n"
        "/- Internal elaboration check only. This axiom is never used as a proof. -/\n"
        f"{declaration}\n\n"
        "open Lean Meta\n\n"
        "run_cmd Lean.Elab.Command.liftTermElabM do\n"
        f"  let declaration ← getConstInfo ``{problem.name}\n"
        "  unless ← isProp declaration.type do\n"
        "    throwError \"generated theorem type is not a proposition\"\n"
    )


def _generated_text(
    generated: str | GenerationResult,
) -> tuple[str, TokenUsage | None, str | None]:
    if isinstance(generated, GenerationResult):
        return generated.text, generated.token_usage, generated.finish_reason
    if isinstance(generated, str):
        return generated, None, None
    raise TypeError("LLM backend must return str or GenerationResult")


def _write_input(
    run_dir: Path,
    problem: NaturalLanguageProblem,
    imports: tuple[str, ...],
    max_formalization_attempts: int,
    max_proof_attempts: int,
) -> None:
    _write_json(
        run_dir / "input.json",
        {
            "name": problem.name,
            "natural_language": problem.text,
            "description": problem.description,
            "category": problem.category,
            "imports": list(imports),
            "max_formalization_attempts": max_formalization_attempts,
            "max_proof_attempts": max_proof_attempts,
        },
    )


def _write_formalization_attempt(
    run_dir: Path, attempt: FormalizationAttempt
) -> None:
    verification = asdict(attempt.verification)
    verification["command"] = list(attempt.verification.command)
    _write_json(
        run_dir / f"formalization_{attempt.number:02d}.json",
        {
            "attempt": attempt.number,
            "raw_response": attempt.raw_response,
            "theorem_statement": attempt.theorem_statement,
            "source_file": attempt.source_path.name,
            "generation_seconds": attempt.generation_seconds,
            "token_usage": asdict(attempt.token_usage) if attempt.token_usage else None,
            "finish_reason": attempt.finish_reason,
            "truncated_by_token_limit": attempt.finish_reason == "length",
            "lean_feedback": (
                None
                if attempt.verification.success
                else attempt.verification.compiler_feedback
            ),
            "verification": verification,
        },
    )


def _write_autoformalization_summary(result: AutoformalizationResult) -> None:
    proof = result.proof_result
    _write_json(
        result.run_dir / "summary.json",
        {
            "problem": result.natural_language_problem.name,
            "success": result.success,
            "formalization_attempt_count": len(result.formalization_attempts),
            "final_theorem": result.final_theorem,
            "proof_run_dir": str(proof.run_dir) if proof else None,
            "proof_attempt_count": len(proof.attempts) if proof else 0,
            "verified_proof": result.verified_proof,
        },
    )


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
