"""Append-only JSON and Lean artifacts for reproducible runs."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid

from .models import AttemptRecord, LeanProblem, RunResult, VerificationResult


def create_run_dir(root: Path, problem_name: str) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", problem_name).strip("-") or "proof"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = root.resolve() / f"{stamp}-{safe_name}-{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def write_problem(run_dir: Path, problem: LeanProblem, max_attempts: int) -> None:
    payload = {
        "name": problem.name,
        "description": problem.description,
        "imports": list(problem.imports),
        "theorem": problem.theorem,
        "max_attempts": max_attempts,
    }
    _write_json(run_dir / "problem.json", payload)


def write_attempt(run_dir: Path, record: AttemptRecord) -> None:
    verification = _verification_dict(record.verification)
    payload = {
        "attempt": record.number,
        "proof": record.proof,
        "source_file": record.source_path.name,
        "verification": verification,
    }
    _write_json(run_dir / f"attempt_{record.number:02d}.json", payload)


def write_summary(result: RunResult) -> None:
    payload = {
        "problem": result.problem.name,
        "success": result.success,
        "attempt_count": len(result.attempts),
        "final_proof": result.final_proof,
        "attempt_files": [f"attempt_{item.number:02d}.json" for item in result.attempts],
    }
    _write_json(result.run_dir / "summary.json", payload)


def _verification_dict(result: VerificationResult) -> dict[str, object]:
    value = asdict(result)
    value["command"] = list(result.command)
    return value


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
