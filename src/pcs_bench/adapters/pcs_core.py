"""Adapter for pcs-core CLI."""

from __future__ import annotations

from pathlib import Path

from pcs_bench.adapters.base import AdapterStatus, CommandResult, RepoAdapter
from pcs_bench.config import BenchConfig


class PcsCoreAdapter(RepoAdapter):
    name = "pcs_core"

    def __init__(self, repo_path: Path, config: BenchConfig):
        super().__init__(repo_path, config)

    def _binary(self) -> str:
        return self.config.commands.pcs

    def validate(self, path: Path) -> CommandResult:
        return self.run([self._binary(), "validate", str(path)])

    def validate_release_chain(self, release_dir: Path) -> CommandResult:
        return self.run([self._binary(), "validate-release-chain", str(release_dir)])

    def conformance_run(self, suite: str) -> CommandResult:
        return self.run([self._binary(), "conformance", "run", "--suite", suite])

    def lean_check(self, obligation_path: Path, out_path: Path) -> CommandResult:
        return self.run(
            [
                self._binary(),
                "lean-check",
                "--obligations",
                str(obligation_path),
                "--out",
                str(out_path),
            ]
        )

    def registry_check_artifact(self, artifact_path: Path) -> CommandResult:
        return self.run([self._binary(), "registry", "check-artifact", str(artifact_path)])

    def run_smoke_check(self) -> AdapterStatus:
        result = self.run([self._binary(), "--help"])
        if result.exit_code == 0:
            return AdapterStatus.AVAILABLE
        return AdapterStatus.SMOKE_FAILED
