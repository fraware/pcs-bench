"""pcs-bench CLI."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from pcs_bench import __version__
from pcs_bench.adapters.base import AdapterStatus
from pcs_bench.baselines import compare_reports, format_comparison_text
from pcs_bench.ci import (
    check_ci_thresholds,
    check_live_required,
    check_repo_commits_resolved,
    format_ci_failure,
)
from pcs_bench.config import ALL_SUITES, SUITE_ALIASES, BenchConfig
from pcs_bench.errors import PcsBenchError, ThresholdViolationError
from pcs_bench.coverage import apply_coverage_to_report
from pcs_bench.metrics import apply_metrics_to_report, compute_all_metrics
from pcs_bench.packet import export_benchmark_packet
from pcs_bench.report_renderers.csv import render_csv
from pcs_bench.report_renderers.html import render_html
from pcs_bench.report_renderers.json import render_json
from pcs_bench.report_renderers.markdown import render_markdown
from pcs_bench.reports import load_report, save_report
from pcs_bench.runners import AdapterRegistry, run_suite
from pcs_bench.suite_policy import collect_suite_policy
from pcs_bench.validation import validate_cases_for_suite
from pcs_bench.workspace import create_run_workspace

app = typer.Typer(
    name="pcs-bench",
    help="Evaluation harness for Proof-Carrying Science (PCS) releases.",
    no_args_is_help=True,
)
console = Console()


def _load_config(config_path: Optional[Path]) -> BenchConfig:
    return BenchConfig.load(config_path)


def _alias_for_internal(name: str) -> str:
    for alias, internal in SUITE_ALIASES.items():
        if internal == name:
            return alias
    return name


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        help="Show version and exit.",
    ),
) -> None:
    if version is True:
        console.print(f"pcs-bench {__version__}")
        raise typer.Exit(0)
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit(0)


@app.command("list-suites")
def list_suites_cmd() -> None:
    """List available benchmark suites."""
    table = Table("CLI alias", "Directory", "Description")
    for internal in ALL_SUITES:
        alias = _alias_for_internal(internal)
        suite_yaml = Path("benchmarks") / internal / "suite.yaml"
        desc = ""
        if suite_yaml.exists():
            import yaml

            data = yaml.safe_load(suite_yaml.read_text(encoding="utf-8")) or {}
            desc = (data.get("description") or "")[:60]
        table.add_row(alias, internal, desc)
    table.add_row("all", "all", "Run every suite")
    console.print(table)


@app.command("check-adapters")
def check_adapters_cmd(
    config: Optional[Path] = typer.Option(None, "--config"),
    pcs_core: Optional[Path] = typer.Option(None, "--pcs-core"),
    labtrust: Optional[Path] = typer.Option(None, "--labtrust"),
    certifyedge: Optional[Path] = typer.Option(None, "--certifyedge"),
    provability_fabric: Optional[Path] = typer.Option(None, "--provability-fabric"),
    scientific_memory: Optional[Path] = typer.Option(None, "--scientific-memory"),
) -> None:
    """Smoke-check ecosystem repo CLIs."""
    cfg = _load_config(config).apply_cli_overrides(
        pcs_core=pcs_core,
        labtrust=labtrust,
        certifyedge=certifyedge,
        provability_fabric=provability_fabric,
        scientific_memory=scientific_memory,
    )
    registry = AdapterRegistry(cfg)
    table = Table("Adapter", "Status", "Commit", "Repo path")
    all_ok = True
    for adapter in registry.all_adapters():
        status = adapter.run_smoke_check()
        if status != AdapterStatus.AVAILABLE:
            all_ok = False
        table.add_row(
            adapter.name,
            status.value,
            adapter.version_or_commit()[:12],
            str(adapter.repo_path),
        )
    console.print(table)
    if not all_ok:
        console.print(
            "[yellow]Some adapters unavailable. Use --simulate for fixture-driven runs.[/yellow]"
        )
        raise typer.Exit(1)


@app.command("run")
def run_cmd(
    suite: str = typer.Option(..., "--suite", help="Suite alias or 'all'."),
    config: Optional[Path] = typer.Option(None, "--config", help="Path to pcs-bench.yaml."),
    out: Path = typer.Option(Path("reports/latest.json"), "--out", help="Output report JSON."),
    workspace: Optional[Path] = typer.Option(None, "--workspace", help="Workspace root override."),
    preserve_workspace: bool = typer.Option(False, "--preserve-workspace"),
    fail_fast: bool = typer.Option(False, "--fail-fast"),
    ci: bool = typer.Option(False, "--ci", help="Fail on threshold violations."),
    verbose: bool = typer.Option(False, "--verbose"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip CLI and artifact analysis."),
    live: bool = typer.Option(False, "--live", help="Invoke live ecosystem CLIs."),
    simulate: bool = typer.Option(
        True,
        "--simulate/--no-simulate",
        help="Use fixture sidecars (default). Ignored when --live is set.",
    ),
    hybrid: bool = typer.Option(
        False,
        "--hybrid",
        help="Try live CLIs first; fall back to fixture simulation when unavailable.",
    ),
    cases: Optional[str] = typer.Option(
        None,
        "--cases",
        help="Comma-separated case IDs to run (default: all in suite).",
    ),
    parallel: Optional[int] = typer.Option(
        None,
        "--parallel",
        help="Override parallel case workers (simulate/dry-run only).",
    ),
    pcs_core: Optional[Path] = typer.Option(None, "--pcs-core"),
    labtrust: Optional[Path] = typer.Option(None, "--labtrust"),
    certifyedge: Optional[Path] = typer.Option(None, "--certifyedge"),
    provability_fabric: Optional[Path] = typer.Option(None, "--provability-fabric"),
    scientific_memory: Optional[Path] = typer.Option(None, "--scientific-memory"),
) -> None:
    """Run benchmark suite(s)."""
    cfg = _load_config(config).apply_cli_overrides(
        pcs_core=pcs_core,
        labtrust=labtrust,
        certifyedge=certifyedge,
        provability_fabric=provability_fabric,
        scientific_memory=scientific_memory,
        workspace=workspace,
    )

    if preserve_workspace:
        cfg.workspace.clean_between_cases = False
    if parallel is not None:
        cfg.execution.parallel_cases = max(1, parallel)

    case_filter = {c.strip() for c in cases.split(",") if c.strip()} if cases else None
    suite_names = cfg.resolve_suites(suite)
    ws = create_run_workspace(cfg, workspace)

    if dry_run:
        console.print("[yellow]Dry run — planning only[/yellow]")
    elif hybrid:
        console.print("[cyan]Hybrid mode — live CLIs with fixture fallback[/cyan]")
    elif live:
        console.print("[green]Live mode — invoking ecosystem CLIs[/green]")
    elif simulate:
        console.print("[cyan]Simulate mode — fixture sidecars + artifact analysis[/cyan]")
    else:
        console.print("[green]Live mode — invoking ecosystem CLIs[/green]")

    console.print(f"[bold]pcs-bench run[/bold] suites={suite_names} workspace={ws.root}")

    merged_runs = []
    last_report = None
    per_suite_scores: dict[str, float] = {}
    required_metrics, optional_metrics, live_required_suites = collect_suite_policy(
        cfg.benchmarks_root, suite_names
    )

    use_simulate = (simulate or not live) and not live and not hybrid
    if ci and live_required_suites and use_simulate and not dry_run:
        console.print(
            "[red]CI with live_required suites requires --live (not --simulate)[/red]"
        )
        raise typer.Exit(1)

    for suite_name in suite_names:
        suite_dir = cfg.benchmarks_root / suite_name
        if not suite_dir.exists():
            console.print(f"[red]Suite directory missing: {suite_dir}[/red]")
            if ci:
                raise typer.Exit(1)
            continue
        console.print(f"\n[bold]Suite:[/bold] {suite_name}")
        report, runs = run_suite(
            cfg,
            suite_dir,
            ws,
            dry_run=dry_run,
            simulate=use_simulate and not dry_run and not hybrid,
            hybrid=hybrid and not dry_run,
            require_live=live and not dry_run and not hybrid,
            fail_fast=fail_fast,
            case_filter=case_filter,
            console=console,
        )
        merged_runs.extend(runs)
        last_report = report
        passed = sum(1 for r in runs if r.passed)
        per_suite_scores[suite_name] = passed / len(runs) if runs else 1.0

    if last_report is None:
        console.print("[red]No suites were executed[/red]")
        raise typer.Exit(1)

    from pcs_bench.schemas import BenchmarkReport as BR

    if len(suite_names) == 1:
        final_report = last_report
    else:
        final_report = BR(
            benchmark_suite_id="all",
            repo_commits=last_report.repo_commits,
            dry_run=dry_run or simulate,
        )
        final_report.runs = merged_runs
        final_report.summary["suites"] = suite_names
        final_report.summary["execution_mode"] = last_report.summary.get("execution_mode", "simulate")
        final_report.summary["simulated_cases"] = sum(
            1 for r in merged_runs if r.execution_kind in (None, "simulate", "dry_run")
        )
        final_report.summary["live_cases"] = sum(
            1 for r in merged_runs if r.execution_kind == "live"
        )
        final_report.summary["hybrid_fallback_cases"] = sum(
            1 for r in merged_runs if r.execution_kind == "hybrid_fallback"
        )

    summaries = compute_all_metrics(
        final_report.runs,
        suite_scores=per_suite_scores,
        required_metrics=required_metrics,
        optional_metrics=optional_metrics,
    )
    apply_metrics_to_report(final_report, summaries)
    apply_coverage_to_report(final_report)

    is_live = live and not dry_run and not hybrid
    final_report.summary["execution_mode"] = (
        "live" if is_live else ("hybrid" if hybrid else ("dry_run" if dry_run else "simulate"))
    )
    final_report.summary["evidence_grade"] = "release" if (ci and is_live) else "developer"
    if is_live:
        final_report.dry_run = False
    elif use_simulate or hybrid or dry_run:
        final_report.dry_run = True

    save_report(final_report, out, pcs_core_path=cfg.repos.pcs_core)
    console.print(f"\n[green]Report written to[/green] {out}")

    from pcs_bench.validation import validate_report_json

    report_errors = validate_report_json(out, cfg, schema_source=cfg.repos.pcs_core)
    if report_errors:
        for err in report_errors:
            console.print(f"  [red]schema[/red] {err}")
        if ci:
            raise typer.Exit(1)

    if verbose:
        table = Table("Metric", "Score", "Applicability")
        for summary in final_report.metric_summaries:
            score_txt = f"{summary.score:.3f}" if summary.score is not None else "n/a"
            table.add_row(summary.name, score_txt, summary.applicability)
        console.print(table)

    if ci:
        violations = check_ci_thresholds(
            final_report, cfg, required_metrics=required_metrics
        )
        live_errors = check_live_required(
            final_report,
            live_required_suites,
            release_grade=final_report.summary.get("evidence_grade") == "release",
        )
        if is_live:
            live_errors.extend(check_repo_commits_resolved(final_report))
        if live_errors:
            for msg in live_errors:
                console.print(f"[red]{msg}[/red]")
            raise typer.Exit(1)
        if violations:
            console.print(format_ci_failure(violations))
            raise typer.Exit(1)

    failed = sum(1 for r in final_report.runs if not r.passed)
    if failed:
        raise typer.Exit(1)


@app.command("init")
def init_cmd(
    path: Path = typer.Option(Path("pcs-bench.yaml"), "--path"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Write default pcs-bench.yaml configuration."""
    from pcs_bench.init_config import write_default_config

    if write_default_config(path, force=force):
        console.print(f"[green]Created[/green] {path}")
    else:
        console.print(f"[yellow]Already exists[/yellow] {path} (use --force to overwrite)")


@app.command("verify-fixtures")
def verify_fixtures_cmd(
    manifest: Path = typer.Option(
        Path("benchmarks/fixture_manifest.json"),
        "--manifest",
    ),
    write: bool = typer.Option(False, "--write", help="Regenerate manifest."),
    config: Optional[Path] = typer.Option(None, "--config"),
) -> None:
    """Verify or generate benchmark fixture integrity manifest."""
    from pcs_bench.reproducibility import (
        build_fixture_manifest,
        save_fixture_manifest,
        verify_fixture_manifest,
    )

    cfg = _load_config(config)
    if write or not manifest.exists():
        m = build_fixture_manifest(cfg)
        save_fixture_manifest(m, manifest)
        console.print(f"[green]Wrote manifest[/green] {manifest} ({m.file_count} files)")
        return
    result = verify_fixture_manifest(cfg, manifest)
    if result.valid:
        console.print("[green]Fixture manifest verified[/green]")
        return
    if result.changed_files:
        console.print(f"[red]Changed files ({len(result.changed_files)}):[/red]")
        for p in result.changed_files[:20]:
            console.print(f"  - {p}")
    if result.new_files:
        console.print(f"[red]New files ({len(result.new_files)}):[/red]")
        for p in result.new_files[:20]:
            console.print(f"  - {p}")
    if result.missing_files:
        console.print(f"[red]Missing files ({len(result.missing_files)}):[/red]")
        for p in result.missing_files[:20]:
            console.print(f"  - {p}")
    raise typer.Exit(1)


@app.command("packet")
def packet_cmd(
    report_path: Path = typer.Option(..., "--report", help="Benchmark report JSON."),
    out: Path = typer.Option(Path("packets/latest"), "--out", help="Output packet directory."),
    baseline: Optional[Path] = typer.Option(None, "--baseline"),
    workspace: Optional[Path] = typer.Option(None, "--workspace", help="Run workspace for logs."),
    config: Optional[Path] = typer.Option(None, "--config"),
) -> None:
    """Export a self-contained benchmark packet for external reviewers."""
    cfg = _load_config(config)
    packet_dir = export_benchmark_packet(
        report_path,
        out,
        cfg,
        baseline_path=baseline,
        workspace_root=workspace,
    )
    console.print(f"[green]Benchmark packet written to[/green] {packet_dir}")


@app.command("validate-report")
def validate_report_cmd(
    input: Path = typer.Option(..., "--input", help="Benchmark report JSON."),
    schema_source: Optional[Path] = typer.Option(
        None,
        "--schema-source",
        help="Path to pcs-core repo for BenchmarkReport.v0 schema.",
    ),
    pcs_core: Optional[Path] = typer.Option(
        None,
        "--pcs-core",
        help="Alias for --schema-source (pcs-core checkout path).",
    ),
    config: Optional[Path] = typer.Option(None, "--config"),
) -> None:
    """Validate a report against pcs-core BenchmarkReport.v0."""
    schema_root = pcs_core or schema_source
    cfg = _load_config(config).apply_cli_overrides(
        pcs_core=schema_root,
    )
    from pcs_bench.validation import validate_report_json

    errors = validate_report_json(input, cfg, schema_source=schema_root)
    if errors:
        console.print("[red]Report validation failed:[/red]")
        for err in errors:
            console.print(f"  - {err}")
        raise typer.Exit(1)
    console.print("[green]Report validates against BenchmarkReport.v0[/green]")


@app.command("sync-schemas")
def sync_schemas_cmd(
    pcs_core: Path = typer.Option(..., "--pcs-core", help="Path to pcs-core repository."),
) -> None:
    """Copy JSON schemas from pcs-core into embedded pcs-bench fallbacks."""
    from pcs_bench.schema_sync import sync_schemas_from_pcs_core

    result = sync_schemas_from_pcs_core(pcs_core)
    if result.errors:
        for err in result.errors:
            console.print(f"[red]{err}[/red]")
        raise typer.Exit(1)
    for name in result.copied:
        console.print(f"[green]Copied[/green] {name}.json")
    if result.missing:
        console.print(f"[dim]Not found in pcs-core:[/dim] {', '.join(result.missing)}")
    console.print("[green]Schema sync complete[/green]")


@app.command("gate")
def gate_cmd(
    config: Optional[Path] = typer.Option(None, "--config"),
    out: Path = typer.Option(Path("reports/ci.json"), "--out"),
    packet_dir: Path = typer.Option(Path("packets/latest"), "--out-packet", "--packet"),
    suite: str = typer.Option("all", "--suite"),
    live: bool = typer.Option(False, "--live", help="Run benchmark gate in live mode."),
    hybrid: bool = typer.Option(
        False,
        "--hybrid",
        help="Try live CLIs first; fall back to fixture simulation when a CLI is missing.",
    ),
    run_producer_benchmarks: bool = typer.Option(
        False,
        "--run-producer-benchmarks",
        help="Run producer-native benchmarks, ingest PcsBenchIngest.v0, and merge into gate report.",
    ),
    use_producer_fixtures: bool = typer.Option(
        False,
        "--use-producer-fixtures",
        help="Use embedded golden ingests when a producer repo has no pcs_bench_ingest.v0.json.",
    ),
    reproduce_smoke: bool = typer.Option(
        False,
        "--reproduce-smoke",
        help="Run packet verify with reproduction smoke checks (valid/invalid/explain/rendering).",
    ),
    pcs_core: Optional[Path] = typer.Option(
        None,
        "--pcs-core",
        help="pcs-core checkout for schema validation (overrides pcs-bench.yaml).",
    ),
    labtrust: Optional[Path] = typer.Option(None, "--labtrust"),
    certifyedge: Optional[Path] = typer.Option(None, "--certifyedge"),
    provability_fabric: Optional[Path] = typer.Option(None, "--provability-fabric"),
    scientific_memory: Optional[Path] = typer.Option(None, "--scientific-memory"),
) -> None:
    """Run full release gate: fixtures, manifest, cases, benchmark, report validation, packet."""
    import subprocess

    cfg = _load_config(config).apply_cli_overrides(
        pcs_core=pcs_core,
        labtrust=labtrust,
        certifyedge=certifyedge,
        provability_fabric=provability_fabric,
        scientific_memory=scientific_memory,
    )
    root = Path.cwd()
    py = sys.executable

    steps = [
        ([py, str(root / "scripts" / "materialize_fixtures.py")], "materialize fixtures"),
        ([py, "-m", "pcs_bench", "verify-fixtures", "--write"], "write fixture manifest"),
        ([py, "-m", "pcs_bench", "verify-fixtures"], "verify fixture manifest"),
        ([py, "-m", "pcs_bench", "validate-cases", "--suite", suite, "--dry-run"], "validate cases"),
        (
            [py, str(root / "scripts" / "validate_producer_ingest_fixtures.py")]
            + (
                ["--pcs-core", str(cfg.repos.pcs_core)]
                if cfg.repos.pcs_core.is_dir()
                else []
            ),
            "validate producer ingest fixtures",
        ),
    ]
    bench_out = out.parent / f"{out.stem}-bench-only.json" if run_producer_benchmarks else out
    run_args = [py, "-m", "pcs_bench", "run", "--suite", suite, "--ci", "--out", str(bench_out)]
    if hybrid:
        run_args.append("--hybrid")
    elif live:
        run_args.append("--live")
    else:
        run_args.append("--simulate")
    steps.append((run_args, "benchmark run"))

    if live and not hybrid:
        from pcs_bench.runners import AdapterRegistry

        registry = AdapterRegistry(cfg)
        statuses = registry.check_all()
        missing = {
            name: status.value
            for name, status in statuses.items()
            if status != AdapterStatus.AVAILABLE
        }
        if missing:
            console.print("[red]Live gate requires all ecosystem adapters.[/red]")
            for name, status in sorted(missing.items()):
                console.print(f"  [dim]{name}[/dim]: {status}")
            console.print(
                "[yellow]Fix CLIs (see: pcs-bench check-adapters) or use "
                "make producer-gate / gate --hybrid for partial live + fixture fallback.[/yellow]"
            )
            raise typer.Exit(1)

    for cmd, label in steps:
        console.print(f"[bold]gate[/bold] {label}")
        proc = subprocess.run(cmd, cwd=root)
        if proc.returncode != 0:
            console.print(f"[red]Gate failed at step:[/red] {label}")
            raise typer.Exit(proc.returncode)

    if run_producer_benchmarks:
        from pcs_bench.producer_gate import aggregate_gate_report

        console.print("[bold]gate[/bold] aggregate producer ingests")
        scratch = out.parent / ".gate-producer-scratch"
        producer_release_grade = (live or hybrid) and not use_producer_fixtures
        agg_errors = aggregate_gate_report(
            cfg,
            bench_out,
            scratch_dir=scratch,
            run_producer_benchmarks=True,
            out_path=out,
            require_all_producers=True,
            use_fixture_fallback=use_producer_fixtures,
            release_grade=producer_release_grade,
        )
        if agg_errors:
            console.print("[red]Producer ingest aggregation failed:[/red]")
            for err in agg_errors:
                console.print(f"  - {err}")
            raise typer.Exit(1)
        if not out.is_file():
            console.print("[red]Gate failed: no aggregate report produced[/red]")
            raise typer.Exit(1)

    validate_report_cmd = [py, "-m", "pcs_bench", "validate-report", "--input", str(out)]
    pcs_core_path = cfg.repos.pcs_core
    if pcs_core_path and pcs_core_path.is_dir():
        validate_report_cmd.extend(["--pcs-core", str(pcs_core_path)])

    post_steps = [
        (validate_report_cmd, "validate report"),
        (
            [py, "-m", "pcs_bench", "packet", "--report", str(out), "--out", str(packet_dir)],
            "export packet",
        ),
        (
            [
                py,
                "-m",
                "pcs_bench",
                "verify-packet",
                "--packet",
                str(packet_dir),
            ]
            + (["--reproduce-smoke"] if reproduce_smoke else []),
            "verify packet",
        ),
    ]
    for cmd, label in post_steps:
        console.print(f"[bold]gate[/bold] {label}")
        proc = subprocess.run(cmd, cwd=root)
        if proc.returncode != 0:
            console.print(f"[red]Gate failed at step:[/red] {label}")
            raise typer.Exit(proc.returncode)

    console.print(f"[green]Gate passed[/green] report={out} packet={packet_dir}")


@app.command("validate-producer-fixtures")
def validate_producer_fixtures_cmd(
    pcs_core: Optional[Path] = typer.Option(None, "--pcs-core"),
    release_grade: bool = typer.Option(
        False,
        "--release-grade",
        help="Also require release-grade semantic adequacy on golden fixtures.",
    ),
    config: Optional[Path] = typer.Option(None, "--config"),
) -> None:
    """Validate all embedded producer PcsBenchIngest.v0 fixtures."""
    from pcs_bench.producer_fixtures import resolve_schema_root, validate_all_producer_fixtures

    cfg = _load_config(config).apply_cli_overrides(pcs_core=pcs_core)
    schema_root = resolve_schema_root(cfg.repos.pcs_core if cfg.repos.pcs_core.is_dir() else None)
    results = validate_all_producer_fixtures(schema_root, release_grade=release_grade)
    failed = False
    for result in results:
        if result.valid:
            console.print(f"[green]OK[/green] {result.producer}")
        else:
            failed = True
            console.print(f"[red]FAIL[/red] {result.producer}")
            for err in result.errors:
                console.print(f"  - {err}")
    if failed:
        raise typer.Exit(1)
    grade = "release-grade" if release_grade else "schema"
    console.print(f"[green]All producer fixtures passed ({grade})[/green]")


@app.command("check-producer-ingests")
def check_producer_ingests_cmd(
    config: Optional[Path] = typer.Option(None, "--config"),
    fixtures_only: bool = typer.Option(
        False,
        "--fixtures-only",
        help="Validate embedded golden fixtures (offline; no sibling repos required).",
    ),
    release_grade: bool = typer.Option(
        False,
        "--release-grade",
        help="Apply release-grade ingest adequacy checks.",
    ),
    pcs_core: Optional[Path] = typer.Option(None, "--pcs-core"),
    labtrust: Optional[Path] = typer.Option(None, "--labtrust"),
    certifyedge: Optional[Path] = typer.Option(None, "--certifyedge"),
    provability_fabric: Optional[Path] = typer.Option(None, "--provability-fabric"),
    scientific_memory: Optional[Path] = typer.Option(None, "--scientific-memory"),
) -> None:
    """Report PcsBenchIngest.v0 presence and validation for each producer repo."""
    from pcs_bench.producer_fixtures import (
        PRODUCER_FIXTURE_DIRS,
        fixture_ingest_path,
        resolve_schema_root,
    )
    from pcs_bench.producer_gate import PRODUCER_BENCHMARKS, _repo_for_producer
    from pcs_bench.ingest_validation import validate_ingest_json

    cfg = _load_config(config).apply_cli_overrides(
        pcs_core=pcs_core,
        labtrust=labtrust,
        certifyedge=certifyedge,
        provability_fabric=provability_fabric,
        scientific_memory=scientific_memory,
    )
    schema_root = resolve_schema_root(cfg.repos.pcs_core if cfg.repos.pcs_core.is_dir() else None)
    table = Table("Producer", "Ingest path", "Status")
    failed = False

    if fixtures_only:
        for producer_id, dirname in PRODUCER_FIXTURE_DIRS:
            path = fixture_ingest_path(dirname)
            if not path.is_file():
                table.add_row(producer_id, str(path), "[red]missing[/red]")
                failed = True
                continue
            errors = validate_ingest_json(
                path, schema_root, release_grade=release_grade
            )
            if errors:
                table.add_row(producer_id, str(path), f"[red]{len(errors)} errors[/red]")
                failed = True
            else:
                status = "[green]valid[/green]"
                if release_grade:
                    status += " (release)"
                table.add_row(producer_id, str(path), status)
        console.print(table)
        if failed:
            raise typer.Exit(1)
        return

    for spec in PRODUCER_BENCHMARKS:
        repo = _repo_for_producer(cfg, spec.producer)
        path = repo / spec.ingest_rel_path
        if not path.is_file():
            from pcs_bench.producer_gate import _embedded_fixture_ingest

            fixture = _embedded_fixture_ingest(spec.producer)
            hint = (
                f" [dim](golden fixture: {fixture})[/dim]"
                if fixture
                else " [dim](run: make sync-ingest-fixtures)[/dim]"
            )
            table.add_row(spec.producer, str(path), f"[red]missing[/red]{hint}")
            failed = True
            continue
        errors = validate_ingest_json(
            path,
            schema_root,
            release_grade=release_grade,
            producer_repo=repo if repo.is_dir() else None,
        )
        if errors:
            table.add_row(spec.producer, str(path), f"[red]{len(errors)} errors[/red]")
            failed = True
        else:
            status = "[green]valid[/green]"
            if release_grade:
                status += " (release)"
            table.add_row(spec.producer, str(path), status)
    console.print(table)
    if failed:
        console.print(
            "[yellow]Producer repos must emit pcs_bench_ingest.v0.json at the paths above. "
            "For offline checks use: pcs-bench check-producer-ingests --fixtures-only[/yellow]"
        )
        raise typer.Exit(1)


@app.command("ingest-all-producers")
def ingest_all_producers_cmd(
    out_dir: Path = typer.Option(Path("reports/producers"), "--out-dir"),
    config: Optional[Path] = typer.Option(None, "--config"),
    pcs_core: Optional[Path] = typer.Option(None, "--pcs-core"),
    labtrust: Optional[Path] = typer.Option(None, "--labtrust"),
    certifyedge: Optional[Path] = typer.Option(None, "--certifyedge"),
    provability_fabric: Optional[Path] = typer.Option(None, "--provability-fabric"),
    scientific_memory: Optional[Path] = typer.Option(None, "--scientific-memory"),
) -> None:
    """Ingest PcsBenchIngest.v0 from all producer repos into normalized reports."""
    from pcs_bench.producer_ingest_all import ingest_all_producers

    cfg = _load_config(config).apply_cli_overrides(
        pcs_core=pcs_core,
        labtrust=labtrust,
        certifyedge=certifyedge,
        provability_fabric=provability_fabric,
        scientific_memory=scientific_memory,
    )
    result = ingest_all_producers(cfg, out_dir)
    for path in result.outputs:
        console.print(f"[green]Wrote[/green] {path}")
    if result.errors:
        console.print("[red]Ingest errors:[/red]")
        for err in result.errors:
            console.print(f"  - {err}")
        raise typer.Exit(1)


@app.command("validate-ingest")
def validate_ingest_cmd(
    input: Path = typer.Option(..., "--input", help="PcsBenchIngest.v0 file or benchmark_runs directory."),
    pcs_core: Optional[Path] = typer.Option(None, "--pcs-core"),
    use_pcs_validate: bool = typer.Option(
        False,
        "--use-pcs-validate",
        help="Also run pcs-core CLI validate when pcs is on PATH.",
    ),
    release_grade: bool = typer.Option(
        False,
        "--release-grade",
        help="Fail on semantic inadequacy (empty runs, missing producer artifacts, placeholder commits).",
    ),
    config: Optional[Path] = typer.Option(None, "--config"),
) -> None:
    """Validate a producer PcsBenchIngest.v0 payload against pcs-core schemas."""
    from pcs_bench.ingest_validation import validate_ingest_developer_warnings, validate_ingest_json

    from pcs_bench.producer_fixtures import resolve_schema_root

    cfg = _load_config(config).apply_cli_overrides(pcs_core=pcs_core)
    schema_root = resolve_schema_root(cfg.repos.pcs_core if cfg.repos.pcs_core.is_dir() else None)

    errors = validate_ingest_json(
        input,
        schema_root,
        use_pcs_validate=use_pcs_validate,
        release_grade=release_grade,
    )
    if not release_grade:
        from pcs_bench.ingest_validation import load_ingest_document

        data, base = load_ingest_document(input)
        roots = (base.resolve(),)
        for warning in validate_ingest_developer_warnings(data, search_roots=roots):
            console.print(f"[yellow]{warning}[/yellow]")
    if errors:
        console.print("[red]Ingest validation failed:[/red]")
        for err in errors:
            console.print(f"  - {err}")
        raise typer.Exit(1)
    grade = "release-grade" if release_grade else "schema"
    console.print(f"[green]Ingest validation passed ({grade})[/green] {input}")


@app.command("producer-doctor")
def producer_doctor_cmd(
    config: Optional[Path] = typer.Option(None, "--config"),
    pcs_core: Optional[Path] = typer.Option(None, "--pcs-core"),
    labtrust: Optional[Path] = typer.Option(None, "--labtrust"),
    certifyedge: Optional[Path] = typer.Option(None, "--certifyedge"),
    provability_fabric: Optional[Path] = typer.Option(None, "--provability-fabric"),
    scientific_memory: Optional[Path] = typer.Option(None, "--scientific-memory"),
    release_grade: bool = typer.Option(
        False,
        "--release-grade",
        help="Also evaluate release-grade ingest adequacy (diagnostic only).",
    ),
    json_out: Optional[Path] = typer.Option(
        None,
        "--json-out",
        help="Write structured JSON report to this path.",
    ),
) -> None:
    """Diagnose producer repo readiness (non-gating)."""
    import json as json_mod

    from pcs_bench.producer_doctor import DoctorCheck, run_producer_doctor
    from pcs_bench.producer_fixtures import resolve_schema_root

    cfg = _load_config(config).apply_cli_overrides(
        pcs_core=pcs_core,
        labtrust=labtrust,
        certifyedge=certifyedge,
        provability_fabric=provability_fabric,
        scientific_memory=scientific_memory,
    )
    schema_root = resolve_schema_root(cfg.repos.pcs_core if cfg.repos.pcs_core.is_dir() else None)
    doctor_result = run_producer_doctor(cfg, schema_root=schema_root, release_grade=release_grade)

    table = Table("Producer", "Ready", "Repo", "Cases", "Ingest", "CLI")
    for producer in doctor_result.producers:
        by_name = {c.name: c for c in producer.checks}
        table.add_row(
            producer.producer_id,
            "[green]yes[/green]" if producer.ready else "[red]no[/red]",
            "ok" if by_name.get("repo_exists", DoctorCheck("", False, "")).ok else "missing",
            by_name.get("benchmark_cases_dir", DoctorCheck("", False, "")).detail[:40],
            "ok" if by_name.get("ingest_present", DoctorCheck("", False, "")).ok else "missing",
            "ok" if by_name.get("cli_smoke", DoctorCheck("", False, "")).ok else "fail",
        )
    console.print(table)

    for producer in doctor_result.producers:
        if producer.ready:
            continue
        console.print(f"[yellow]{producer.producer_id}[/yellow]")
        for check in producer.checks:
            if not check.ok:
                console.print(f"  [red]{check.name}[/red]: {check.detail}")

    payload = doctor_result.to_dict()
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json_mod.dumps(payload, indent=2), encoding="utf-8")
        console.print(f"[dim]Wrote JSON report to[/dim] {json_out}")
    else:
        console.print(json_mod.dumps(payload, indent=2))

    if not payload.get("all_ready"):
        raise typer.Exit(2)


@app.command("verify-packet")
def verify_packet_cmd(
    packet: Path = typer.Option(..., "--packet", help="Packet directory."),
    reproduce_smoke: bool = typer.Option(
        False,
        "--reproduce-smoke",
        help="Re-run simulate checks for valid/invalid cases, explain, and rendering.",
    ),
    config: Optional[Path] = typer.Option(None, "--config"),
) -> None:
    """Verify benchmark packet structure and reproducibility fixtures."""
    from pcs_bench.packet import verify_benchmark_packet

    cfg = _load_config(config)
    result = verify_benchmark_packet(packet, cfg, reproduce_smoke=reproduce_smoke)
    if result.warnings:
        for w in result.warnings:
            console.print(f"[yellow]{w}[/yellow]")
    if not result.valid:
        console.print("[red]Packet verification failed:[/red]")
        for err in result.errors:
            console.print(f"  - {err}")
        raise typer.Exit(1)
    console.print("[green]Packet verification passed[/green]")


@app.command("report")
def report_cmd(
    input: Path = typer.Option(..., "--input", help="Input BenchmarkReport JSON."),
    format: str = typer.Option("markdown", "--format", help="markdown|html|csv|json"),
    out: Path = typer.Option(..., "--out", help="Output path."),
    baseline: Optional[Path] = typer.Option(None, "--baseline", help="Baseline for regression section."),
) -> None:
    """Generate human-readable report from BenchmarkReport JSON."""
    report = load_report(input)
    comparison_text = ""
    if baseline and baseline.exists():
        comparison_text = format_comparison_text(compare_reports(load_report(baseline), report))

    fmt = format.lower()
    if fmt == "markdown":
        content = render_markdown(report, comparison_text=comparison_text)
    elif fmt == "html":
        content = render_html(report, comparison_text=comparison_text, config=_load_config(None))
    elif fmt == "csv":
        content = render_csv(report)
    elif fmt == "json":
        content = render_json(report)
    else:
        console.print(f"[red]Unknown format: {format}[/red]")
        raise typer.Exit(1)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    console.print(f"[green]Report written to[/green] {out}")


@app.command("compare")
def compare_cmd(
    old: Path = typer.Option(..., "--old", help="Baseline report JSON."),
    new: Path = typer.Option(..., "--new", help="New report JSON."),
    out: Optional[Path] = typer.Option(None, "--out", help="Optional output file."),
    format: str = typer.Option("text", "--format", help="text|json"),
) -> None:
    """Compare two benchmark reports."""
    import json

    from pcs_bench.baselines import comparison_to_dict

    old_report = load_report(old)
    new_report = load_report(new)
    comparison = compare_reports(old_report, new_report)
    if format.lower() == "json":
        payload = json.dumps(comparison_to_dict(comparison), indent=2)
        if out:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(payload, encoding="utf-8")
        else:
            console.print(payload)
    else:
        text = format_comparison_text(comparison)
        console.print(text)
        if out:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")


@app.command("validate-cases")
def validate_cases_cmd(
    suite: str = typer.Option(..., "--suite", help="Suite alias or 'all'."),
    config: Optional[Path] = typer.Option(None, "--config"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip pcs validate calls."),
    pcs_core: Optional[Path] = typer.Option(None, "--pcs-core"),
) -> None:
    """Validate benchmark case manifests."""
    cfg = _load_config(config).apply_cli_overrides(pcs_core=pcs_core)
    suite_names = cfg.resolve_suites(suite)
    all_valid = True

    for suite_name in suite_names:
        suite_dir = cfg.benchmarks_root / suite_name
        console.print(f"[bold]Validating[/bold] {suite_name}")
        result = validate_cases_for_suite(cfg, suite_dir, dry_run=dry_run)
        for vr in result.results:
            status = "[green]OK[/green]" if vr.valid else "[red]FAIL[/red]"
            console.print(f"  {status} {vr.case_id}")
            for err in vr.errors:
                console.print(f"    - {err}")
            if not vr.valid:
                all_valid = False

    if not all_valid:
        raise typer.Exit(1)


@app.command("ingest-producer-output")
def ingest_producer_output_cmd(
    producer: str = typer.Option(..., "--producer", help="Producer id (certifyedge, provability-fabric, scientific-memory)."),
    input: Path = typer.Option(
        ...,
        "--input",
        help="PcsBenchIngest.v0 file or producer benchmark_runs directory.",
    ),
    out: Path = typer.Option(..., "--out", help="Normalized BenchmarkReport.v0 output path."),
    suite: Optional[str] = typer.Option(None, "--suite", help="Override benchmark_suite_id."),
    pcs_core: Optional[Path] = typer.Option(None, "--pcs-core"),
    config: Optional[Path] = typer.Option(None, "--config"),
) -> None:
    """Normalize a producer-native benchmark report into pcs-bench BenchmarkReport.v0."""
    from pcs_bench.producer_ingest import ingest_producer_output

    cfg = _load_config(config).apply_cli_overrides(pcs_core=pcs_core)
    try:
        report = ingest_producer_output(
            producer,
            input,
            out,
            pcs_core_path=cfg.repos.pcs_core,
            suite_id=suite,
        )
    except (ValueError, FileNotFoundError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    from pcs_bench.validation import validate_report_json

    errors = validate_report_json(out, cfg, schema_source=cfg.repos.pcs_core)
    if errors:
        console.print("[red]Ingested report failed validation:[/red]")
        for err in errors:
            console.print(f"  - {err}")
        raise typer.Exit(1)

    console.print(
        f"[green]Wrote normalized report[/green] {out} "
        f"({len(report.runs)} runs, suite={report.benchmark_suite_id})"
    )


@app.command("explain")
def explain_cmd(
    report_path: Path = typer.Option(..., "--report", help="Benchmark report JSON."),
    case: str = typer.Option(..., "--case", help="Case ID to explain."),
) -> None:
    """Explain a failed benchmark case."""
    report = load_report(report_path)
    run = next((r for r in report.runs if r.case_id == case), None)
    if not run:
        console.print(f"[red]Case not found in report: {case}[/red]")
        raise typer.Exit(1)

    failure = next((f for f in report.failures if f.case_id == case), None)

    console.print(f"[bold]Case ID:[/bold] {run.case_id}")
    console.print(f"[bold]Expected outcome:[/bold] {run.expected_status}")
    console.print(f"[bold]Observed outcome:[/bold] {run.observed_status}")
    console.print(f"[bold]Expected failure code:[/bold] {run.expected_failure_code}")
    console.print(f"[bold]Observed failure code:[/bold] {run.observed_failure_code}")
    console.print(f"[bold]First failing command:[/bold] {run.first_failing_command or 'n/a'}")
    console.print(f"[bold]Responsible repo:[/bold] {run.responsible_repo or 'n/a'}")
    console.print(
        f"[bold]Expected responsible component:[/bold] {run.expected_responsible_component}"
    )
    console.print(
        f"[bold]Observed responsible component:[/bold] {run.observed_responsible_component}"
    )
    console.print(f"[bold]Repair hint:[/bold] {run.observed_repair_hint or 'n/a'}")
    console.print(f"[bold]Repair hint acceptable:[/bold] {run.repair_hint_acceptable}")
    if failure:
        console.print(f"[bold]Logs path:[/bold] {failure.logs_path}")
        console.print(f"[bold]Artifacts path:[/bold] {failure.artifacts_path}")


def main_entry() -> None:
    try:
        app()
    except PcsBenchError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)
    except ThresholdViolationError as exc:
        console.print(f"[red]CI failed:[/red] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main_entry()
