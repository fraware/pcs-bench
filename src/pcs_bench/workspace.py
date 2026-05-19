"""Isolated workspace management for benchmark runs."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from pcs_bench.adapters.base import CommandResult
from pcs_bench.config import BenchConfig
from pcs_bench.schemas import BenchmarkCase


class RunWorkspace:
    """Per-run isolated workspace under .pcs-bench-workspaces/."""

    def __init__(self, root: Path, run_id: str | None = None):
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.run_id = run_id or f"run-{ts}"
        self.root = root / self.run_id
        self.repos = self.root / "repos"
        self.cases = self.root / "cases"
        self.outputs = self.root / "outputs"
        self.logs = self.root / "logs"
        self.reports = self.root / "reports"

    def create(self) -> None:
        for d in (self.repos, self.cases, self.outputs, self.logs, self.reports):
            d.mkdir(parents=True, exist_ok=True)

    def case_workspace(self, case_id: str) -> CaseWorkspace:
        return CaseWorkspace(self.cases / f"case-{case_id}")


class CaseWorkspace:
    def __init__(self, root: Path):
        self.root = root
        self.input = root / "input"
        self.output = root / "output"
        self.logs = root / "logs"
        self.artifacts = root / "artifacts"
        self.command_history_path = root / "command_history.json"

    def create(self) -> None:
        for d in (self.input, self.output, self.logs, self.artifacts):
            d.mkdir(parents=True, exist_ok=True)

    def stage_case_inputs(self, case: BenchmarkCase, suite_dir: Path) -> None:
        for key, rel_path in case.input_artifacts.items():
            src = (suite_dir / rel_path).resolve()
            if not src.exists():
                continue
            dest = self.input / key
            if src.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(src, dest)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)

    def record_commands(self, commands: list[CommandResult]) -> None:
        data = [c.to_dict() for c in commands]
        with self.command_history_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def write_log(self, name: str, content: str) -> Path:
        path = self.logs / name
        path.write_text(content, encoding="utf-8")
        return path


def create_run_workspace(config: BenchConfig, workspace_override: Path | None = None) -> RunWorkspace:
    root = workspace_override or config.workspace.root
    ws = RunWorkspace(root.resolve())
    ws.create()
    return ws


def cleanup_case_workspace(
    case_ws: CaseWorkspace,
    *,
    passed: bool,
    preserve_failed: bool,
) -> None:
    if passed and preserve_failed is False:
        shutil.rmtree(case_ws.root, ignore_errors=True)
