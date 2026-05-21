"""Base adapter for external PCS ecosystem CLIs."""

from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from pcs_bench.config import BenchConfig


class AdapterStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    SMOKE_FAILED = "smoke_failed"


@dataclass
class CommandResult:
    command: list[str]
    cwd: Path
    exit_code: int
    stdout: str
    stderr: str
    started_at: datetime
    completed_at: datetime
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["cwd"] = str(self.cwd)
        d["started_at"] = self.started_at.isoformat()
        d["completed_at"] = self.completed_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CommandResult:
        return cls(
            command=data["command"],
            cwd=Path(data["cwd"]),
            exit_code=data["exit_code"],
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            started_at=datetime.fromisoformat(data["started_at"]),
            completed_at=datetime.fromisoformat(data["completed_at"]),
            duration_ms=data["duration_ms"],
        )


class RepoAdapter:
    """Calls external repo CLIs and records every command."""

    name: str = "base"

    def __init__(self, repo_path: Path, config: BenchConfig):
        self.repo_path = repo_path.resolve()
        self.config = config
        self.command_history: list[CommandResult] = []

    @property
    def timeout_seconds(self) -> int:
        return self.config.timeouts.command_seconds

    def check_available(self) -> AdapterStatus:
        result = self.run([self._binary(), "--help"], cwd=self.repo_path)
        if result.exit_code == 0:
            return AdapterStatus.AVAILABLE
        return AdapterStatus.UNAVAILABLE

    def version_or_commit(self) -> str:
        if not self.repo_path.exists():
            return "unknown"
        git_dir = self.repo_path / ".git"
        if not git_dir.exists():
            return "unknown"
        result = self.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
        )
        if result.exit_code == 0:
            return result.stdout.strip()
        return "unknown"

    def run_smoke_check(self) -> AdapterStatus:
        return self.check_available()

    def _binary(self) -> str:
        raise NotImplementedError

    def run(
        self,
        command: list[str],
        cwd: Path | None = None,
        *,
        env: dict[str, str] | None = None,
        dry_run: bool = False,
    ) -> CommandResult:
        work_dir = (cwd or self.repo_path).resolve()
        started = datetime.now(timezone.utc)

        if dry_run:
            completed = datetime.now(timezone.utc)
            result = CommandResult(
                command=command,
                cwd=work_dir,
                exit_code=0,
                stdout="[dry-run]",
                stderr="",
                started_at=started,
                completed_at=completed,
                duration_ms=0,
            )
            self.command_history.append(result)
            return result

        try:
            proc = subprocess.run(
                command,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=env,
            )
            exit_code = proc.returncode
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
        except subprocess.TimeoutExpired as exc:
            exit_code = 124
            stdout = exc.stdout or "" if exc.stdout else ""
            stderr = (exc.stderr or "") + f"\nCommand timed out after {self.timeout_seconds}s"
        except FileNotFoundError:
            exit_code = 127
            stdout = ""
            stderr = f"Command not found: {command[0]}"

        completed = datetime.now(timezone.utc)
        duration_ms = int((completed - started).total_seconds() * 1000)
        result = CommandResult(
            command=command,
            cwd=work_dir,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            started_at=started,
            completed_at=completed,
            duration_ms=duration_ms,
        )
        self.command_history.append(result)
        return result

    def clear_history(self) -> None:
        self.command_history.clear()


class AdapterCheckResult(BaseModel):
    name: str
    status: AdapterStatus
    version_or_commit: str
    repo_path: str
