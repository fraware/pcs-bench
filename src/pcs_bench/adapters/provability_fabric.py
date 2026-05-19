"""Adapter for provability-fabric (PF) CLI."""

from __future__ import annotations

from pathlib import Path

from pcs_bench.adapters.base import AdapterStatus, CommandResult, RepoAdapter
from pcs_bench.config import BenchConfig


class ProvabilityFabricAdapter(RepoAdapter):
    name = "provability_fabric"

    def __init__(self, repo_path: Path, config: BenchConfig):
        super().__init__(repo_path, config)

    def _binary(self) -> str:
        return self.config.commands.pf

    def verify_science_claim(
        self,
        bundle: Path,
        handoff: Path,
        registry: Path,
        admission_profile: Path,
        out: Path,
        release_chain_result: Path | None = None,
    ) -> CommandResult:
        cmd = [
            self._binary(),
            "verify",
            "science-claim",
            str(bundle),
            "--handoff",
            str(handoff),
            "--registry",
            str(registry),
            "--admission-profile",
            str(admission_profile),
            "--out",
            str(out),
            "--release-mode",
        ]
        if release_chain_result:
            cmd.extend(["--release-chain-result", str(release_chain_result)])
        return self.run(cmd)

    def verify_release_chain(
        self,
        manifest: Path,
        artifact_dir: Path,
        registry: Path,
        out: Path,
    ) -> CommandResult:
        return self.run(
            [
                self._binary(),
                "verify",
                "release-chain",
                "--manifest",
                str(manifest),
                "--artifact-dir",
                str(artifact_dir),
                "--registry",
                str(registry),
                "--out",
                str(out),
                "--release-mode",
            ]
        )

    def explain_release_chain(self, validation_result: Path) -> CommandResult:
        return self.run(
            [self._binary(), "explain", "release-chain", str(validation_result), "--json"]
        )

    def benchmark_admission(self, cases: Path, registry: Path, out_dir: Path) -> CommandResult:
        return self.run(
            [
                self._binary(),
                "benchmark",
                "admission",
                "--cases",
                str(cases),
                "--registry",
                str(registry),
                "--out",
                str(out_dir),
            ]
        )

    def run_smoke_check(self) -> AdapterStatus:
        result = self.run([self._binary(), "--help"])
        if result.exit_code == 0:
            return AdapterStatus.AVAILABLE
        return AdapterStatus.SMOKE_FAILED
