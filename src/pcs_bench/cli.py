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
from pcs_bench.ci import check_ci_thresholds, format_ci_failure
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


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit."),
) -> None:
    if version:
        console.print(f"pcs-bench {__version__}")
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
    simulate: bool = typer.Option(
        True,
        "--simulate/--live",
        help="Simulate from fixture sidecars (default) or invoke live CLIs.",
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
    elif simulate:
        console.print("[cyan]Simulate mode — fixture sidecars + artifact analysis[/cyan]")
    else:
        console.print("[green]Live mode — invoking ecosystem CLIs[/green]")

    console.print(f"[bold]pcs-bench run[/bold] suites={suite_names} workspace={ws.root}")

    merged_runs = []
    last_report = None
    per_suite_scores: dict[str, float] = {}

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
            simulate=simulate and not dry_run and not hybrid,
            hybrid=hybrid and not dry_run,
            require_live=not simulate and not dry_run and not hybrid,
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

    summaries = compute_all_metrics(final_report.runs, suite_scores=per_suite_scores)
    apply_metrics_to_report(final_report, summaries)
    apply_coverage_to_report(final_report)

    save_report(final_report, out)
    console.print(f"\n[green]Report written to[/green] {out}")

    from pcs_bench.validation import validate_report_json

    report_errors = validate_report_json(out, cfg)
    if report_errors:
        console.print("[yellow]Report schema warnings:[/yellow]")
        for err in report_errors:
            console.print(f"  - {err}")

    if verbose:
        table = Table("Metric", "Score")
        for name, score in final_report.metrics.items():
            table.add_row(name, f"{score:.3f}")
        console.print(table)

    if ci:
        violations = check_ci_thresholds(final_report, cfg)
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
    config: Optional[Path] = typer.Option(None, "--config"),
) -> None:
    """Export a self-contained benchmark packet for external reviewers."""
    cfg = _load_config(config)
    packet_dir = export_benchmark_packet(
        report_path, out, cfg, baseline_path=baseline
    )
    console.print(f"[green]Benchmark packet written to[/green] {packet_dir}")


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
