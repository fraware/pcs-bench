"""Adapter for scientific-memory (via just recipes)."""

from __future__ import annotations

import os
from pathlib import Path

from pcs_bench.adapters.base import AdapterStatus, CommandResult, RepoAdapter
from pcs_bench.config import BenchConfig


class ScientificMemoryAdapter(RepoAdapter):
    name = "scientific_memory"

    def __init__(self, repo_path: Path, config: BenchConfig):
        super().__init__(repo_path, config)

    def _binary(self) -> str:
        return self.config.commands.just

    def _run_just(self, recipe: str, env_vars: dict[str, str]) -> CommandResult:
        env = {**os.environ, **env_vars}
        return self.run([self._binary(), recipe], cwd=self.repo_path, env=env)

    def import_release(self, manifest: Path) -> CommandResult:
        return self._run_just(
            "pcs-import-release",
            {"RELEASE_MANIFEST": str(manifest.resolve())},
        )

    def render_claim(self, claim_id: str) -> CommandResult:
        return self._run_just("pcs-render-claim", {"CLAIM_ID": claim_id})

    def check_stale(self, claim_id: str) -> CommandResult:
        return self._run_just("pcs-check-stale", {"CLAIM_ID": claim_id})

    def compare_releases(self, old_release: Path, new_release: Path) -> CommandResult:
        return self._run_just(
            "pcs-compare-releases",
            {
                "OLD_RELEASE": str(old_release.resolve()),
                "NEW_RELEASE": str(new_release.resolve()),
            },
        )

    def benchmark_rendering(self, cases: Path, out_dir: Path) -> CommandResult:
        return self._run_just(
            "pcs-benchmark-rendering",
            {
                "CASES": str(cases.resolve()),
                "OUT": str(out_dir.resolve()),
            },
        )

    def run_smoke_check(self) -> AdapterStatus:
        result = self.run([self._binary(), "--list"], cwd=self.repo_path)
        if result.exit_code == 0:
            return AdapterStatus.AVAILABLE
        return AdapterStatus.SMOKE_FAILED
