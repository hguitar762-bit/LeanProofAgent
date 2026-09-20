"""Subprocess boundary for real Lean verification."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import time

from .models import VerificationResult


class LeanNotFoundError(RuntimeError):
    """Raised when Lake is unavailable."""


def find_lake() -> str:
    """Find Lake on PATH, with an Elan fallback useful on Windows."""

    executable = shutil.which("lake")
    if executable:
        return executable
    fallback = Path.home() / ".elan" / "bin" / (
        "lake.exe" if os.name == "nt" else "lake"
    )
    if fallback.is_file():
        return str(fallback)
    raise LeanNotFoundError(
        "lake was not found; install Lean via Elan and ensure ~/.elan/bin is on PATH"
    )


class LeanVerifier:
    """Verify a source file with ``lake env lean`` in a pinned Lake project."""

    def __init__(
        self,
        project_root: Path,
        *,
        timeout_seconds: float = 120.0,
        lake_executable: str | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.timeout_seconds = timeout_seconds
        self.lake_executable = lake_executable or find_lake()
        if not (self.project_root / "lakefile.toml").is_file() and not (
            self.project_root / "lakefile.lean"
        ).is_file():
            raise ValueError(f"not a Lake project: {self.project_root}")

    def verify(self, source_path: Path) -> VerificationResult:
        source = source_path.resolve()
        command = (self.lake_executable, "env", "lean", str(source))
        environment = os.environ.copy()
        environment.setdefault("NO_COLOR", "1")
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=self.project_root,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.monotonic() - started
            return VerificationResult(
                success=False,
                command=command,
                exit_code=None,
                stdout=_decode_timeout_output(exc.stdout),
                stderr=_decode_timeout_output(exc.stderr),
                duration_seconds=duration,
                timed_out=True,
            )
        duration = time.monotonic() - started
        return VerificationResult(
            success=completed.returncode == 0,
            command=command,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_seconds=duration,
        )


def _decode_timeout_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
