"""
Go test / build / vet runner.

All commands are executed via ``subprocess`` with a timeout.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

_TIMEOUT = 300  # seconds


@dataclass
class RunResult:
    """Outcome of a subprocess invocation."""
    command: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0

    @property
    def output(self) -> str:
        """Combined output (stdout + stderr) for LLM consumption."""
        parts: list[str] = []
        if self.stdout.strip():
            parts.append(self.stdout.strip())
        if self.stderr.strip():
            parts.append(self.stderr.strip())
        return "\n".join(parts) or "(no output)"


def _run(cmd: list[str], cwd: str) -> RunResult:
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            env={**os.environ, "CGO_ENABLED": "0"},
        )
        return RunResult(
            command=" ".join(cmd),
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
    except FileNotFoundError:
        return RunResult(
            command=" ".join(cmd),
            returncode=-1,
            stdout="",
            stderr=f"Command not found: {cmd[0]}. Is Go installed?",
        )
    except subprocess.TimeoutExpired:
        return RunResult(
            command=" ".join(cmd),
            returncode=-2,
            stdout="",
            stderr=f"Command timed out after {_TIMEOUT}s",
        )


def run_go_build(repo_path: str) -> RunResult:
    """Run ``go build ./...`` to verify compilation."""
    return _run(["go", "build", "./..."], cwd=repo_path)


def run_go_vet(repo_path: str) -> RunResult:
    """Run ``go vet ./...`` for static analysis."""
    return _run(["go", "vet", "./..."], cwd=repo_path)


def run_go_test(repo_path: str, package: str = "./...") -> RunResult:
    """Run ``go test`` on the given package (default: all)."""
    return _run(["go", "test", "-count=1", "-timeout=120s", package], cwd=repo_path)


def run_all_checks(repo_path: str) -> dict:
    """Run build + vet + test and return a summary dict.

    Returns
    -------
    dict
        Keys: ``build``, ``vet``, ``test`` → :class:`RunResult`
        Key ``passed`` → bool (all three passed)
        Key ``errors`` → list[str] of failure details
    """
    build = run_go_build(repo_path)
    vet   = run_go_vet(repo_path)
    test  = run_go_test(repo_path)

    errors: list[str] = []
    if not build.passed:
        errors.append(f"BUILD FAILED:\n{build.output}")
    if not vet.passed:
        errors.append(f"VET FAILED:\n{vet.output}")
    if not test.passed:
        errors.append(f"TEST FAILED:\n{test.output}")

    return {
        "build": build,
        "vet": vet,
        "test": test,
        "passed": len(errors) == 0,
        "errors": errors,
    }
