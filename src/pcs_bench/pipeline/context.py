"""Per-case execution context shared across pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pcs_bench.adapters.base import CommandResult
from pcs_bench.artifacts import ArtifactAnalysis
from pcs_bench.schemas import BenchmarkCase, BenchmarkSuite
from pcs_bench.workspace import CaseWorkspace

if TYPE_CHECKING:
    from pcs_bench.runners import AdapterRegistry


class ExecutionMode(str, Enum):
    LIVE = "live"
    DRY_RUN = "dry_run"
    SIMULATE = "simulate"
    HYBRID = "hybrid"


@dataclass
class ObservedOutcome:
    status: str = "Unknown"
    failure_code: str | None = None
    responsible_component: str | None = None
    repair_hint: str | None = None
    repair_hint_kind: str | None = None


@dataclass
class CaseExecutionContext:
    case: BenchmarkCase
    case_ws: CaseWorkspace
    suite: BenchmarkSuite
    suite_dir: Path
    release_dir: Path
    adapters: AdapterRegistry
    mode: ExecutionMode
    run_id: str = field(default_factory=lambda: f"bench-run-{uuid4().hex[:8]}")
    commands: list[CommandResult] = field(default_factory=list)
    observed: ObservedOutcome = field(default_factory=ObservedOutcome)
    analysis: ArtifactAnalysis | None = None
    verification_path: Path | None = None
    release_chain_path: Path | None = None
    rendered_path: Path | None = None
    claim_id: str | None = None
    skip_external: bool = False
    stage_notes: dict[str, str] = field(default_factory=dict)
    used_simulation_fallback: bool = False

    def record(self, result: CommandResult) -> None:
        self.commands.append(result)

    def extend_commands(self, adapter_commands: list[CommandResult]) -> None:
        self.commands.extend(adapter_commands)

    def should_invoke_cli(self) -> bool:
        return self.mode in (ExecutionMode.LIVE, ExecutionMode.HYBRID) and not self.skip_external

    def output_path(self, name: str) -> Path:
        return self.case_ws.output / name
