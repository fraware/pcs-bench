"""Benchmark case and suite execution."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING

from pcs_bench.adapters import (
    CertifyEdgeAdapter,
    LabTrustAdapter,
    PcsCoreAdapter,
    ProvabilityFabricAdapter,
    ScientificMemoryAdapter,
)
from pcs_bench.adapters.base import AdapterStatus
from pcs_bench.config import BenchConfig
from pcs_bench.errors import AdapterUnavailableError
from pcs_bench.pipeline.context import ExecutionMode
from pcs_bench.pipeline.registry import run_case_pipeline
from pcs_bench.schemas import BenchmarkCase, BenchmarkReport, BenchmarkRun, RepoCommits
from pcs_bench.schemas.benchmark import BenchmarkSuite, FailureRecord
from pcs_bench.suites import load_suite, load_suite_cases
from pcs_bench.workspace import CaseWorkspace, RunWorkspace, cleanup_case_workspace

if TYPE_CHECKING:
    from rich.console import Console


class AdapterRegistry:
    def __init__(self, config: BenchConfig, dry_run: bool = False):
        self.dry_run = dry_run
        self.pcs_core = PcsCoreAdapter(config.repos.pcs_core, config)
        self.labtrust = LabTrustAdapter(config.repos.labtrust, config)
        self.certifyedge = CertifyEdgeAdapter(config.repos.certifyedge, config)
        self.pf = ProvabilityFabricAdapter(config.repos.provability_fabric, config)
        self.scientific_memory = ScientificMemoryAdapter(config.repos.scientific_memory, config)

    def all_adapters(self):
        return [
            self.pcs_core,
            self.labtrust,
            self.certifyedge,
            self.pf,
            self.scientific_memory,
        ]

    def check_all(self) -> dict[str, AdapterStatus]:
        return {a.name: a.run_smoke_check() for a in self.all_adapters()}

    def require_all_for_live(self) -> None:
        statuses = self.check_all()
        missing = [k for k, v in statuses.items() if v != AdapterStatus.AVAILABLE]
        if missing:
            raise AdapterUnavailableError(
                f"Live run requires all adapters; unavailable: {', '.join(missing)}. "
                "Use --simulate for fixture-driven evaluation."
            )

    def repo_commits(self) -> RepoCommits:
        from pcs_bench.report_export import pcs_bench_source_commit

        return RepoCommits(
            pcs_core=self.pcs_core.version_or_commit(),
            labtrust=self.labtrust.version_or_commit(),
            certifyedge=self.certifyedge.version_or_commit(),
            provability_fabric=self.pf.version_or_commit(),
            scientific_memory=self.scientific_memory.version_or_commit(),
            pcs_bench=pcs_bench_source_commit(),
        )


def _resolve_mode(
    *,
    dry_run: bool,
    simulate: bool,
    hybrid: bool,
    require_live: bool,
) -> ExecutionMode:
    if dry_run:
        return ExecutionMode.DRY_RUN
    if hybrid:
        return ExecutionMode.HYBRID
    if simulate:
        return ExecutionMode.SIMULATE
    if require_live:
        return ExecutionMode.LIVE
    return ExecutionMode.SIMULATE


def _execute_one_case(
    case: BenchmarkCase,
    case_id: str,
    suite: BenchmarkSuite,
    suite_dir: Path,
    workspace: RunWorkspace,
    mode: ExecutionMode,
    config: BenchConfig,
) -> tuple[BenchmarkRun, FailureRecord | None, CaseWorkspace]:
    adapters = AdapterRegistry(config)
    case_ws = workspace.case_workspace(case_id)
    case_ws.create()
    run = run_case_pipeline(case, case_ws, adapters, suite, suite_dir, mode=mode)
    failure = None
    if not run.passed:
        failure = FailureRecord(
            case_id=case.case_id,
            suite_id=suite.suite_id,
            reason=(
                f"expected {case.expected_status} ({case.expected_failure_code}), "
                f"observed {run.observed_status} ({run.observed_failure_code})"
            ),
            responsible_repo=run.responsible_repo,
            responsible_component=run.observed_responsible_component,
            repair_hint=run.observed_repair_hint,
            logs_path=str(case_ws.logs),
            artifacts_path=str(case_ws.artifacts),
        )
    if not run.passed and not config.workspace.preserve_failed_cases:
        cleanup_case_workspace(
            case_ws,
            passed=False,
            preserve_failed=config.workspace.preserve_failed_cases,
        )
    return run, failure, case_ws


def run_suite(
    config: BenchConfig,
    suite_dir: Path,
    workspace: RunWorkspace,
    *,
    dry_run: bool = False,
    simulate: bool = True,
    hybrid: bool = False,
    require_live: bool = False,
    fail_fast: bool = False,
    case_filter: set[str] | None = None,
    console: Console | None = None,
) -> tuple[BenchmarkReport, list[BenchmarkRun]]:
    from rich.console import Console as RichConsole

    console = console or RichConsole()
    suite = load_suite(suite_dir)
    mode = _resolve_mode(
        dry_run=dry_run, simulate=simulate, hybrid=hybrid, require_live=require_live
    )
    adapters = AdapterRegistry(config, dry_run=dry_run)

    if mode == ExecutionMode.LIVE:
        adapters.require_all_for_live()
    elif mode in (ExecutionMode.SIMULATE, ExecutionMode.HYBRID):
        statuses = adapters.check_all()
        unavailable = [k for k, v in statuses.items() if v != AdapterStatus.AVAILABLE]
        if unavailable:
            console.print(
                f"[dim]Simulate mode — using fixture sidecars "
                f"(adapters unavailable: {unavailable})[/dim]"
            )

    report = BenchmarkReport(
        benchmark_suite_id=suite.suite_id,
        repo_commits=adapters.repo_commits(),
        dry_run=(mode != ExecutionMode.LIVE),
    )
    report.summary["execution_mode"] = mode.value

    case_items = [
        (case_id, case_path, case)
        for case_id, case_path, case in load_suite_cases(suite_dir, suite)
        if not case_filter or case_id in case_filter
    ]

    runs: list[BenchmarkRun] = []
    workers = max(1, config.execution.parallel_cases)
    if workers > 1 and mode not in (ExecutionMode.SIMULATE, ExecutionMode.DRY_RUN):
        console.print("[yellow]Parallel cases only in simulate/dry-run; using 1 worker[/yellow]")
        workers = 1

    def _run_item(item: tuple[str, Path, BenchmarkCase]) -> tuple[BenchmarkRun, FailureRecord | None]:
        cid, _, case = item
        run, failure, _ = _execute_one_case(case, cid, suite, suite_dir, workspace, mode, config)
        return run, failure

    if workers == 1:
        for case_id, _path, _case in case_items:
            console.print(f"  [cyan]case[/cyan] {case_id}")
            run, failure = _run_item((case_id, _path, _case))
            runs.append(run)
            report.runs.append(run)
            if failure:
                report.failures.append(failure)
            if fail_fast and not run.passed:
                break
    else:
        console.print(f"  [dim]Running {len(case_items)} cases with {workers} workers[/dim]")
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_run_item, item): item[0] for item in case_items}
            for future in as_completed(futures):
                case_id = futures[future]
                run, failure = future.result()
                console.print(
                    f"  [cyan]case[/cyan] {case_id} "
                    f"[{'green' if run.passed else 'red'}]{'PASS' if run.passed else 'FAIL'}[/]"
                )
                runs.append(run)
                report.runs.append(run)
                if failure:
                    report.failures.append(failure)

    runs.sort(key=lambda r: r.case_id)
    report.runs = runs
    simulated = sum(1 for r in runs if r.execution_kind in (None, "simulate", "dry_run"))
    live = sum(1 for r in runs if r.execution_kind == "live")
    hybrid_fb = sum(1 for r in runs if r.execution_kind == "hybrid_fallback")
    report.summary.update(
        {
            "execution_mode": mode.value,
            "simulated_cases": simulated,
            "live_cases": live,
            "hybrid_fallback_cases": hybrid_fb,
        }
    )
    return report, runs
