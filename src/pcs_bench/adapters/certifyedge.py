"""Adapter for CertifyEdge CLI."""

from __future__ import annotations

from pathlib import Path

from pcs_bench.adapters.base import AdapterStatus, CommandResult, RepoAdapter
from pcs_bench.config import BenchConfig


class CertifyEdgeAdapter(RepoAdapter):
    name = "certifyedge"

    def __init__(self, repo_path: Path, config: BenchConfig):
        super().__init__(repo_path, config)

    def _binary(self) -> str:
        return self.config.commands.certifyedge

    def emit_certificate(
        self,
        handoff: Path,
        profile_registry: Path,
        out: Path,
        handoff_out: Path,
    ) -> CommandResult:
        return self.run(
            [
                self._binary(),
                "emit-pcs-certificate",
                "--release-mode",
                "--handoff",
                str(handoff),
                "--profile-registry",
                str(profile_registry),
                "--out",
                str(out),
                "--handoff-out",
                str(handoff_out),
            ]
        )

    def validate_profiles(self, profile_dir: Path) -> CommandResult:
        return self.run([self._binary(), "profiles", "validate", str(profile_dir)])

    def benchmark_certificates(self, profile: str, cases: Path, out_dir: Path) -> CommandResult:
        return self.run(
            [
                self._binary(),
                "benchmark",
                "certificates",
                "--profile",
                profile,
                "--cases",
                str(cases),
                "--out",
                str(out_dir),
            ]
        )

    def run_smoke_check(self) -> AdapterStatus:
        result = self.run([self._binary(), "--help"])
        if result.exit_code == 0:
            return AdapterStatus.AVAILABLE
        return AdapterStatus.SMOKE_FAILED
