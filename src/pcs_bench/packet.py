"""Export and verify public benchmark packets for external reviewers."""

from __future__ import annotations

import json
import platform
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from pcs_bench.config import BenchConfig
from pcs_bench.report_export import to_benchmark_report_v0_dict
from pcs_bench.report_renderers.csv import render_csv
from pcs_bench.report_renderers.html import render_html
from pcs_bench.report_renderers.markdown import render_markdown
from pcs_bench.reports import load_report
from pcs_bench.schemas import BenchmarkReport


PACKET_REQUIRED_FILES = [
    "BenchmarkReport.v0.json",
    "report.md",
    "report.html",
    "summary.csv",
    "case_manifest.json",
    "environment_summary.json",
    "limitations.md",
    "reproduce.sh",
]


@dataclass
class PacketVerificationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def export_benchmark_packet(
    report_path: Path,
    out_dir: Path,
    config: BenchConfig | None = None,
    *,
    baseline_path: Path | None = None,
    workspace_root: Path | None = None,
) -> Path:
    """Create a self-contained reviewer packet directory."""
    report = load_report(report_path)
    cfg = config or BenchConfig()
    out_dir = out_dir.resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    comparison_text = ""
    if baseline_path and baseline_path.exists():
        from pcs_bench.baselines import compare_reports, format_comparison_text

        comparison_text = format_comparison_text(
            compare_reports(load_report(baseline_path), report)
        )

    payload = to_benchmark_report_v0_dict(report)
    (out_dir / "BenchmarkReport.v0.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    (out_dir / "report.md").write_text(
        render_markdown(report, comparison_text=comparison_text),
        encoding="utf-8",
    )
    (out_dir / "report.html").write_text(
        render_html(report, comparison_text=comparison_text),
        encoding="utf-8",
    )
    (out_dir / "summary.csv").write_text(render_csv(report), encoding="utf-8")

    cases_dir = out_dir / "cases"
    cases_dir.mkdir()
    manifest_cases: list[dict] = []
    benchmarks_root = cfg.benchmarks_root.resolve()

    for run in report.runs:
        case_ref = _find_case_fixture(benchmarks_root, run.case_id)
        if case_ref:
            dest = cases_dir / run.case_id
            shutil.copytree(case_ref.parent, dest, dirs_exist_ok=True)
            manifest_cases.append(
                {
                    "case_id": run.case_id,
                    "suite_id": run.suite_id,
                    "passed": run.passed,
                    "expected_status": run.expected_status,
                    "observed_status": run.observed_status,
                    "fixture_path": str(dest.relative_to(out_dir)),
                }
            )

    (out_dir / "case_manifest.json").write_text(
        json.dumps(manifest_cases, indent=2),
        encoding="utf-8",
    )

    _export_command_history(report, out_dir / "command_history.json")
    _export_logs(report, workspace_root, out_dir / "logs")
    _write_environment_summary(report, out_dir / "environment_summary.json")
    _write_repo_commits(report, out_dir / "repo_commits.json")
    (out_dir / "limitations.md").write_text(_limitations_md(report), encoding="utf-8")
    (out_dir / "README.md").write_text(_reviewer_readme(report, out_dir), encoding="utf-8")
    _write_reproduce_script(out_dir)

    meta = {
        "packet_version": "v0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "report_id": report.report_id,
        "digest": report.signature_or_digest,
        "execution_mode": report.summary.get("execution_mode", "unknown"),
        "simulated_cases": report.summary.get("simulated_cases"),
        "live_cases": report.summary.get("live_cases"),
    }
    (out_dir / "packet_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return out_dir


def verify_benchmark_packet(packet_dir: Path, config: BenchConfig | None = None) -> PacketVerificationResult:
    """Verify packet structure and that valid/invalid fixtures are reproducible."""
    cfg = config or BenchConfig()
    packet_dir = packet_dir.resolve()
    result = PacketVerificationResult(valid=True)

    for name in PACKET_REQUIRED_FILES:
        if not (packet_dir / name).exists():
            result.errors.append(f"Missing required packet file: {name}")
            result.valid = False

    report_path = packet_dir / "BenchmarkReport.v0.json"
    if report_path.exists():
        from pcs_bench.validation import validate_report_data_strict

        data = json.loads(report_path.read_text(encoding="utf-8"))
        schema_errors = validate_report_data_strict(data, cfg.repos.pcs_core)
        for err in schema_errors:
            result.errors.append(err)
            result.valid = False

    manifest_path = packet_dir / "case_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        from pcs_bench.benchmark_vocabulary import BENCHMARK_FAILED, BENCHMARK_PASSED

        valid_cases = [c for c in manifest if c.get("expected_status") == BENCHMARK_PASSED]
        invalid_cases = [c for c in manifest if c.get("expected_status") == BENCHMARK_FAILED]
        if not valid_cases:
            result.errors.append("Packet must include at least one valid (passed) case fixture")
            result.valid = False
        if not invalid_cases:
            result.errors.append("Packet must include at least one invalid (failed) case fixture")
            result.valid = False
        for entry in manifest:
            rel = entry.get("fixture_path")
            if rel and not (packet_dir / rel).exists():
                result.errors.append(f"Fixture missing for case {entry.get('case_id')}: {rel}")
                result.valid = False
            elif rel:
                case_json = packet_dir / rel / "benchmark_case.v0.json"
                if not case_json.exists():
                    result.errors.append(f"benchmark_case.v0.json missing under {rel}")
                    result.valid = False

    return result


def _export_command_history(report: BenchmarkReport, dest: Path) -> None:
    history = []
    for run in report.runs:
        for cmd in run.commands:
            history.append(
                {
                    "case_id": run.case_id,
                    "command": cmd.command,
                    "cwd": cmd.cwd,
                    "exit_code": cmd.exit_code,
                    "duration_ms": cmd.duration_ms,
                }
            )
    dest.write_text(json.dumps(history, indent=2), encoding="utf-8")


def _export_logs(report: BenchmarkReport, workspace_root: Path | None, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if not workspace_root or not workspace_root.exists():
        (dest / "README.txt").write_text(
            "No workspace logs captured; re-run with preserved workspace for full logs.",
            encoding="utf-8",
        )
        return
    for log_path in workspace_root.rglob("*.log"):
        try:
            rel = log_path.relative_to(workspace_root)
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(log_path, target)
        except (OSError, ValueError):
            continue


def _write_environment_summary(report: BenchmarkReport, dest: Path) -> None:
    summary = {
        "python_version": sys.version,
        "platform": platform.platform(),
        "executable": sys.executable,
        "report_id": report.report_id,
        "benchmark_suite_id": report.benchmark_suite_id,
        "execution_mode": report.summary.get("execution_mode"),
        "repo_commits": report.repo_commits.model_dump(),
    }
    dest.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def _write_repo_commits(report: BenchmarkReport, dest: Path) -> None:
    dest.write_text(json.dumps(report.repo_commits.model_dump(), indent=2), encoding="utf-8")


def _limitations_md(report: BenchmarkReport) -> str:
    mode = report.summary.get("execution_mode", "simulate")
    return f"""# Benchmark limitations

This packet was produced by pcs-bench, an external evaluation harness. It does not
define PCS schemas, workflows, certificates, PF admission rules, or Lean theorems.

## Execution mode

- Mode: `{mode}`
- Simulated cases: {report.summary.get("simulated_cases", "n/a")}
- Live cases: {report.summary.get("live_cases", "n/a")}
- Hybrid fallback cases: {report.summary.get("hybrid_fallback_cases", "n/a")}

## Simulation caveats

When execution_mode is simulate or hybrid with fallback, outcomes are driven by
fixture `expected/` sidecars and artifact analysis. Scores for dimensions without
relevant cases are marked insufficient_cases or not_applicable rather than 1.0.

## Reproducibility scope

`reproduce.sh` re-runs simulate mode against bundled fixtures. Live reproduction
requires sibling PCS repositories and their CLIs on PATH.

Report digest: `{report.signature_or_digest or "n/a"}`
"""


def _find_case_fixture(benchmarks_root: Path, case_id: str) -> Path | None:
    for case_file in benchmarks_root.rglob("benchmark_case.v0.json"):
        try:
            data = json.loads(case_file.read_text(encoding="utf-8"))
            if data.get("case_id") == case_id:
                return case_file
        except (json.JSONDecodeError, OSError):
            continue
    return None


def _reviewer_readme(report: BenchmarkReport, out_dir: Path) -> str:
    return f"""# PCS Benchmark Packet

Report `{report.report_id}` exported for external review.

## Contents

| File | Description |
|------|-------------|
| `BenchmarkReport.v0.json` | Machine-readable benchmark report (pcs-core schema) |
| `report.md` / `report.html` | Human-readable summaries |
| `summary.csv` | Per-case CSV |
| `cases/` | Fixture inputs used for each case |
| `case_manifest.json` | Case index with pass/fail |
| `command_history.json` | Recorded CLI invocations |
| `logs/` | Per-case command logs when workspace preserved |
| `environment_summary.json` | Host and Python environment |
| `repo_commits.json` | Observed sibling repo commits |
| `limitations.md` | Simulation and scope caveats |
| `reproduce.sh` | Re-run simulate benchmark |

## Verify packet

```bash
pcs-bench verify-packet --packet {out_dir.name}
```

## Reproduce

```bash
pip install -e ".[dev]"
python scripts/materialize_fixtures.py
bash reproduce.sh
```

Digest: `{report.signature_or_digest or "n/a"}`
"""


def _write_reproduce_script(out_dir: Path) -> None:
    sh = """#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"
pip install -e ".[dev]" >/dev/null 2>&1 || pip install -e ".[dev]"
python scripts/materialize_fixtures.py
python -m pcs_bench run --suite all --simulate --out reports/repro.json
python -m pcs_bench compare --old "$SCRIPT_DIR/BenchmarkReport.v0.json" --new reports/repro.json
python -m pcs_bench verify-packet --packet "$SCRIPT_DIR"
echo "Reproduction complete."
"""
    ps1 = """$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
Set-Location $Root
pip install -e ".[dev]"
python scripts/materialize_fixtures.py
python -m pcs_bench run --suite all --simulate --out reports/repro.json
python -m pcs_bench compare --old (Join-Path $ScriptDir "BenchmarkReport.v0.json") -new reports/repro.json
python -m pcs_bench verify-packet --packet $ScriptDir
Write-Host "Reproduction complete."
"""
    sh_path = out_dir / "reproduce.sh"
    sh_path.write_text(sh, encoding="utf-8")
    try:
        sh_path.chmod(0o755)
    except OSError:
        pass
    (out_dir / "reproduce.ps1").write_text(ps1, encoding="utf-8")
