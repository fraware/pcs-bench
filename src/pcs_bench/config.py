"""Configuration loading and CLI overrides."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from pcs_bench.errors import ConfigError

SUITE_ALIASES: dict[str, str] = {
    "labtrust-qc-release": "labtrust_qc_release",
    "tool-use-safety": "tool_use_safety",
    "computation-reproducibility": "computation_reproducibility",
    "formal-trust-kernel": "formal_trust_kernel",
    "scientific-memory-rendering": "scientific_memory_rendering",
    "cross-domain": "cross_domain",
    "all": "all",
}

ALL_SUITES = [
    "labtrust_qc_release",
    "tool_use_safety",
    "computation_reproducibility",
    "formal_trust_kernel",
    "scientific_memory_rendering",
    "cross_domain",
]


class RepoPaths(BaseModel):
    pcs_core: Path = Path("../pcs-core")
    labtrust: Path = Path("../LabTrust-Gym")
    certifyedge: Path = Path("../CertifyEdge")
    provability_fabric: Path = Path("../provability-fabric")
    scientific_memory: Path = Path("../scientific-memory")


class CommandNames(BaseModel):
    pcs: str = "pcs"
    labtrust: str = "labtrust"
    certifyedge: str = "certifyedge"
    pf: str = "pf"
    just: str = "just"


class WorkspaceConfig(BaseModel):
    root: Path = Path(".pcs-bench-workspaces")
    clean_between_cases: bool = True
    preserve_failed_cases: bool = True


class Thresholds(BaseModel):
    release_reproducibility_score: float = 0.95
    failure_localization_accuracy: float = 0.90
    certificate_completeness_score: float = 0.95
    registry_coverage_score: float = 0.95
    formal_check_coverage_score: float = 0.90
    scientific_memory_interpretability_score: float = 0.95
    repair_hint_quality_score: float = 0.90
    cross_domain_portability_score: float = 0.90


class Timeouts(BaseModel):
    command_seconds: int = 120
    suite_seconds: int = 1800


class ExecutionConfig(BaseModel):
    parallel_cases: int = 1


class BenchConfig(BaseModel):
    repos: RepoPaths = Field(default_factory=RepoPaths)
    commands: CommandNames = Field(default_factory=CommandNames)
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    thresholds: Thresholds = Field(default_factory=Thresholds)
    timeouts: Timeouts = Field(default_factory=Timeouts)
    benchmarks_root: Path = Path("benchmarks")
    reports_root: Path = Path("reports")

    @classmethod
    def load(cls, config_path: Path | None = None) -> BenchConfig:
        path = config_path or Path("pcs-bench.yaml")
        if not path.exists():
            return cls()
        with path.open(encoding="utf-8") as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}
        return cls.model_validate(raw)

    def resolve_suite_dir(self, suite_alias: str) -> Path:
        internal = SUITE_ALIASES.get(suite_alias, suite_alias)
        if internal == "all":
            raise ConfigError("Use resolve_suites() for 'all'")
        return self.benchmarks_root / internal

    def resolve_suites(self, suite_alias: str) -> list[str]:
        internal = SUITE_ALIASES.get(suite_alias, suite_alias)
        if internal == "all":
            return list(ALL_SUITES)
        return [internal]

    def apply_cli_overrides(
        self,
        *,
        pcs_core: Path | None = None,
        labtrust: Path | None = None,
        certifyedge: Path | None = None,
        provability_fabric: Path | None = None,
        scientific_memory: Path | None = None,
        workspace: Path | None = None,
    ) -> BenchConfig:
        data = self.model_dump()
        if pcs_core:
            data["repos"]["pcs_core"] = str(pcs_core.resolve())
        if labtrust:
            data["repos"]["labtrust"] = str(labtrust.resolve())
        if certifyedge:
            data["repos"]["certifyedge"] = str(certifyedge.resolve())
        if provability_fabric:
            data["repos"]["provability_fabric"] = str(provability_fabric.resolve())
        if scientific_memory:
            data["repos"]["scientific_memory"] = str(scientific_memory.resolve())
        if workspace:
            data["workspace"]["root"] = str(workspace.resolve())
        return BenchConfig.model_validate(data)
