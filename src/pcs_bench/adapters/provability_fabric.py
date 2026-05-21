"""Adapter for provability-fabric (PF) CLI."""

from __future__ import annotations

from pathlib import Path

from pcs_bench.adapters.base import (
    AdapterStatus,
    CommandResult,
    RepoAdapter,
    resolve_executable,
)
from pcs_bench.config import BenchConfig


class ProvabilityFabricAdapter(RepoAdapter):
    name = "provability_fabric"

    def __init__(self, repo_path: Path, config: BenchConfig):
        super().__init__(repo_path, config)
        self._cli_prefix_cache: list[str] | None = None

    def _binary(self) -> str:
        return self.config.commands.pf

    def _cli_prefix(self) -> list[str]:
        if self._cli_prefix_cache is not None:
            return self._cli_prefix_cache
        configured = self.config.commands.pf
        found = resolve_executable(configured)
        if found != configured:
            self._cli_prefix_cache = [found]
            return self._cli_prefix_cache
        pf_dir = (self.repo_path / "core" / "cli" / "pf").resolve()
        if (pf_dir / "go.mod").is_file():
            self._cli_prefix_cache = ["go", "run", "-C", str(pf_dir), "."]
            return self._cli_prefix_cache
        self._cli_prefix_cache = [configured]
        return self._cli_prefix_cache

    def _pf_cmd(self, *args: str) -> list[str]:
        return [*self._cli_prefix(), *args]

    def verify_science_claim(
        self,
        bundle: Path,
        handoff: Path,
        registry: Path,
        admission_profile: Path,
        out: Path,
        release_chain_result: Path | None = None,
    ) -> CommandResult:
        cmd = self._pf_cmd(
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
        )
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
            self._pf_cmd(
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
            )
        )

    def explain_release_chain(self, validation_result: Path) -> CommandResult:
        return self.run(
            self._pf_cmd("explain", "release-chain", str(validation_result), "--json")
        )

    def benchmark_admission(self, cases: Path, registry: Path, out_dir: Path) -> CommandResult:
        return self.run(
            self._pf_cmd(
                "benchmark",
                "admission",
                "--cases",
                str(cases),
                "--registry",
                str(registry),
                "--out",
                str(out_dir),
            )
        )

    def run_smoke_check(self) -> AdapterStatus:
        result = self.run(self._pf_cmd("--help"))
        if result.exit_code == 0:
            return AdapterStatus.AVAILABLE
        return AdapterStatus.SMOKE_FAILED
