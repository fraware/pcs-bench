"""Adapter for LabTrust-Gym CLI."""

from __future__ import annotations

from pathlib import Path

from pcs_bench.adapters.base import AdapterStatus, CommandResult, RepoAdapter, resolve_executable
from pcs_bench.config import BenchConfig


class LabTrustAdapter(RepoAdapter):
    name = "labtrust"

    def __init__(self, repo_path: Path, config: BenchConfig):
        super().__init__(repo_path, config)

    def _binary(self) -> str:
        return resolve_executable(self.config.commands.labtrust)

    def regenerate_release_protocol(self, out_dir: Path) -> CommandResult:
        return self.run(
            [
                self._binary(),
                "regenerate-release-protocol",
                "--pcs-core",
                str(self.config.repos.pcs_core),
                "--certifyedge-bin",
                self.config.commands.certifyedge,
                "--out",
                str(out_dir),
            ]
        )

    def verify_release_protocol(self, release_dir: Path) -> CommandResult:
        return self.run(
            [
                self._binary(),
                "verify-release-protocol",
                "--release-dir",
                str(release_dir),
                "--pcs-core",
                str(self.config.repos.pcs_core),
            ]
        )

    def generate_benchmark_cases(self, workflow: str, out_dir: Path) -> CommandResult:
        return self.run(
            [
                self._binary(),
                "generate-benchmark-cases",
                "--workflow",
                workflow,
                "--out",
                str(out_dir),
            ]
        )

    def benchmark_reproducibility(self, runs: int, out_dir: Path) -> CommandResult:
        return self.run(
            [
                self._binary(),
                "benchmark-reproducibility",
                "--pcs-core",
                str(self.config.repos.pcs_core),
                "--certifyedge-bin",
                self.config.commands.certifyedge,
                "--runs",
                str(runs),
                "--out",
                str(out_dir),
            ]
        )

    def run_smoke_check(self) -> AdapterStatus:
        result = self.run([self._binary(), "--help"])
        if result.exit_code == 0:
            return AdapterStatus.AVAILABLE
        return AdapterStatus.SMOKE_FAILED
