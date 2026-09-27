"""Compiler-in-the-loop proof generation."""

from __future__ import annotations

from pathlib import Path
import time
from typing import Protocol

from .artifacts import create_run_dir, write_attempt, write_problem, write_summary
from .llm import LLMBackend, normalize_proof
from .models import (
    AttemptRecord,
    GenerationResult,
    LeanProblem,
    RunResult,
    VerificationResult,
)
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .premise_retrieval import PremiseRetriever, write_premises


class ProofGenerationError(RuntimeError):
    """Backend failure carrying proof attempts completed before the failure."""

    def __init__(self, cause: Exception, partial_result: RunResult) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.partial_result = partial_result


class ProofVerifier(Protocol):
    """Compiler interface consumed by the agent."""

    def verify(self, source_path: Path) -> VerificationResult:
        """Check one generated Lean source file."""


class ProofAgent:
    """Generate, verify, and repair Lean proofs for a bounded number of attempts."""

    def __init__(
        self,
        backend: LLMBackend,
        verifier: ProofVerifier,
        *,
        max_attempts: int = 3,
        artifacts_root: Path = Path("runs"),
        premise_retriever: PremiseRetriever | None = None,
        premise_top_k: int = 10,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.backend = backend
        self.verifier = verifier
        self.max_attempts = max_attempts
        self.artifacts_root = artifacts_root
        if premise_top_k < 1:
            raise ValueError("premise_top_k must be at least 1")
        self.premise_retriever = premise_retriever
        self.premise_top_k = premise_top_k

    def solve(self, problem: LeanProblem) -> RunResult:
        run_dir = create_run_dir(self.artifacts_root, problem.name)
        write_problem(run_dir, problem, self.max_attempts)
        premises = ()
        if self.premise_retriever is not None:
            premises = self.premise_retriever.retrieve(
                problem, top_k=self.premise_top_k
            )
            write_premises(run_dir / "premises.json", premises)
        records: list[AttemptRecord] = []
        previous_proof: str | None = None
        compiler_error: str | None = None

        for number in range(1, self.max_attempts + 1):
            prompt = build_user_prompt(
                problem,
                attempt_number=number,
                previous_proof=previous_proof,
                compiler_error=compiler_error,
                premises=premises,
            )
            generation_started = time.monotonic()
            try:
                generated = self.backend.generate(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=prompt,
                )
            except Exception as exc:
                partial_result = RunResult(problem, False, tuple(records), run_dir)
                write_summary(partial_result)
                raise ProofGenerationError(exc, partial_result) from exc
            generation_seconds = time.monotonic() - generation_started
            if isinstance(generated, GenerationResult):
                raw_response = generated.text
                token_usage = generated.token_usage
                finish_reason = generated.finish_reason
            elif isinstance(generated, str):
                raw_response = generated
                token_usage = None
                finish_reason = None
            else:
                raise TypeError("LLM backend must return str or GenerationResult")
            try:
                proof = normalize_proof(raw_response)
                source_text = problem.source_with(proof)
            except ValueError as exc:
                proof = raw_response.strip()
                source_path = run_dir / f"attempt_{number:02d}.lean"
                source_path.write_text(
                    f"/- Rejected before Lean invocation: {exc} -/\n", encoding="utf-8"
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
                source_path = run_dir / f"attempt_{number:02d}.lean"
                source_path.write_text(source_text, encoding="utf-8")
                verification = self.verifier.verify(source_path)

            record = AttemptRecord(
                number=number,
                proof=proof,
                source_path=source_path,
                verification=verification,
                generation_seconds=generation_seconds,
                token_usage=token_usage,
                finish_reason=finish_reason,
            )
            records.append(record)
            write_attempt(run_dir, record)
            if verification.success:
                result = RunResult(problem, True, tuple(records), run_dir)
                write_summary(result)
                return result
            previous_proof = proof
            compiler_error = verification.compiler_feedback

        result = RunResult(problem, False, tuple(records), run_dir)
        write_summary(result)
        return result
