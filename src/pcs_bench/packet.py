"""Export and verify public benchmark packets for external reviewers."""

from __future__ import annotations

import json
import platform
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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

    payload = to_benchmark_report_v0_dict(report, pcs_core_path=cfg.repos.pcs_core)
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
    explain = (report.coverage or {}).get("explain_quality")
    if isinstance(explain, dict):
        (out_dir / "explain_quality.json").write_text(
            json.dumps(explain, indent=2),
            encoding="utf-8",
        )
    _export_producer_coverage_artifacts(report_path, out_dir)
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

    from pcs_bench.producer_artifacts import attach_producer_artifacts_for_packet

    attach_producer_artifacts_for_packet(
        report_path, out_dir, scratch_dir=report_path.parent / ".gate-producer-scratch"
    )
    return out_dir


def verify_benchmark_packet(
    packet_dir: Path,
    config: BenchConfig | None = None,
    *,
    reproduce_smoke: bool = False,
) -> PacketVerificationResult:
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

    if reproduce_smoke:
        smoke_report = _verify_reproduce_smoke(packet_dir, result)
        smoke_path = packet_dir / "packet_reproduction_report.v0.json"
        smoke_path.write_text(json.dumps(smoke_report, indent=2), encoding="utf-8")
        if not smoke_report.get("passed", False):
            result.valid = False

    return result


def _verify_reproduce_smoke(
    packet_dir: Path,
    result: PacketVerificationResult,
) -> dict[str, Any]:
    """Re-run lightweight reproduction checks; return packet_reproduction_report.v0 payload."""
    from pcs_bench.benchmark_vocabulary import BENCHMARK_FAILED, BENCHMARK_PASSED
    from pcs_bench.cases import load_case
    from pcs_bench.metrics_definitions import REQUIRED_MEMORY_SECTIONS
    from pcs_bench.simulation import load_expected_sidecar, simulate_outcome

    checks: dict[str, Any] = {}
    manifest_path = packet_dir / "case_manifest.json"
    if not manifest_path.exists():
        result.errors.append("reproduce-smoke: case_manifest.json missing")
        result.valid = False
        return _reproduction_report_payload(packet_dir, checks, passed=False)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    valid_entry = next(
        (c for c in manifest if c.get("expected_status") == BENCHMARK_PASSED),
        None,
    )
    invalid_entry = next(
        (c for c in manifest if c.get("expected_status") == BENCHMARK_FAILED),
        None,
    )
    if not valid_entry or not invalid_entry:
        result.errors.append("reproduce-smoke: need one valid and one invalid case in manifest")
        result.valid = False
        checks["labtrust_valid_replay"] = {"ok": False, "detail": "missing valid case"}
        checks["labtrust_invalid_rejection"] = {"ok": False, "detail": "missing invalid case"}
    else:
        for key, label, entry in (
            ("labtrust_valid_replay", "valid", valid_entry),
            ("labtrust_invalid_rejection", "invalid", invalid_entry),
        ):
            rel = entry.get("fixture_path")
            if not rel:
                result.errors.append(f"reproduce-smoke: {label} case missing fixture_path")
                result.valid = False
                checks[key] = {"ok": False, "detail": "missing fixture_path"}
                continue
            case_root = packet_dir / rel
            case_json = case_root / "benchmark_case.v0.json"
            if not case_json.exists():
                result.errors.append(f"reproduce-smoke: {label} case missing benchmark_case.v0.json")
                result.valid = False
                checks[key] = {"ok": False, "detail": "missing benchmark_case.v0.json"}
                continue
            case = load_case(case_json)
            outcome = simulate_outcome(case, case_root)
            expected_pass = entry.get("expected_status") == BENCHMARK_PASSED
            ok = True
            if expected_pass and outcome.system_outcome != (case.expected_system_outcome or "admitted"):
                result.errors.append(
                    f"reproduce-smoke: valid case {case.case_id} did not reproduce admitted outcome"
                )
                result.valid = False
                ok = False
            if not expected_pass and outcome.system_outcome == "admitted":
                result.errors.append(
                    f"reproduce-smoke: invalid case {case.case_id} unexpectedly admitted"
                )
                result.valid = False
                ok = False
            checks[key] = {
                "ok": ok,
                "case_id": case.case_id,
                "observed_system_outcome": outcome.system_outcome,
            }

    producer_checks = _verify_producer_coverage_smoke(packet_dir, result)
    checks.update(producer_checks)

    render_case = next(
        (
            c
            for c in manifest
            if (packet_dir / str(c.get("fixture_path", "")) / "expected" / "rendered_sections.json").exists()
        ),
        None,
    )
    if not render_case:
        result.errors.append("reproduce-smoke: no Scientific Memory rendering fixture in packet")
        result.valid = False
        checks["scientific_memory_rendering"] = {"ok": False, "detail": "no rendering fixture"}
    else:
        rel = render_case["fixture_path"]
        rendered = load_expected_sidecar(packet_dir / rel, "rendered_sections.json")
        sections = rendered.get("sections") or rendered.get("rendered_sections") or []
        missing = [s for s in REQUIRED_MEMORY_SECTIONS if s not in sections]
        render_ok = not missing
        if missing:
            result.errors.append(
                f"reproduce-smoke: rendering case missing sections {missing}"
            )
            result.valid = False
        checks["scientific_memory_rendering"] = {
            "ok": render_ok,
            "case_id": render_case.get("case_id"),
            "sections_present": list(sections),
            "missing_sections": missing,
        }

    check_values = [c.get("ok") for c in checks.values() if isinstance(c, dict)]
    passed = bool(check_values) and all(check_values)
    if not passed:
        result.valid = False
    return _reproduction_report_payload(packet_dir, checks, passed=passed)


_COVERAGE_EXPORT_KEYS = (
    "explain_quality",
    "profile_coverage",
    "certificate_completeness",
    "registry",
    "formal_checks",
)


def _write_coverage_block(dest: Path, filename: str, block: Any) -> None:
    if isinstance(block, dict) and block:
        (dest / filename).write_text(json.dumps(block, indent=2), encoding="utf-8")


def _export_producer_coverage_from_ingest(dest: Path, ingest_data: dict[str, Any]) -> None:
    """Export coverage artifacts from a PcsBenchIngest.v0 document."""
    from pcs_bench.producer_ingest import _coverage_block_from_ingest

    coverage = _coverage_block_from_ingest(ingest_data)
    for key in _COVERAGE_EXPORT_KEYS:
        _write_coverage_block(dest, f"{key}.json", coverage.get(key, {}))

    explain_reports = ingest_data.get("explain_quality_reports") or []
    if explain_reports and isinstance(explain_reports[0], dict):
        _write_coverage_block(dest, "explain_quality.json", explain_reports[0])

    profile_reports = ingest_data.get("profile_coverage_reports") or []
    if profile_reports and isinstance(profile_reports[0], dict):
        _write_coverage_block(dest, "profile_coverage.json", profile_reports[0])


def _export_producer_coverage_artifacts(report_path: Path, out_dir: Path) -> None:
    """Export per-producer coverage blocks from merge manifest normalized reports."""
    manifest_path = out_dir / "producer_merge_manifest.v0.json"
    if not manifest_path.is_file():
        manifest_path = report_path.parent / "producer_merge_manifest.v0.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    producer_root = out_dir / "producer_coverage"
    for entry in manifest.get("producer_reports") or []:
        if not isinstance(entry, dict):
            continue
        producer_id = str(entry.get("producer_id", ""))
        if not producer_id:
            continue
        dest = producer_root / producer_id
        dest.mkdir(parents=True, exist_ok=True)

        ingest_raw = entry.get("ingest_path")
        if ingest_raw:
            ingest_path = Path(ingest_raw)
            if ingest_path.is_file():
                ingest_data = json.loads(ingest_path.read_text(encoding="utf-8"))
                _export_producer_coverage_from_ingest(dest, ingest_data)
                continue

        normalized = entry.get("normalized_path")
        if not normalized:
            continue
        norm_path = Path(normalized)
        if not norm_path.is_file():
            continue
        data = json.loads(norm_path.read_text(encoding="utf-8"))
        coverage = data.get("coverage") or {}
        for key in _COVERAGE_EXPORT_KEYS:
            _write_coverage_block(dest, f"{key}.json", coverage.get(key, {}))


def _verify_producer_coverage_smoke(
    packet_dir: Path,
    result: PacketVerificationResult,
) -> dict[str, Any]:
    """Validate PF/SM explain-quality and CertifyEdge profile coverage when exported."""
    from pcs_bench.validation.schema_loader import validate_instance

    pcs_root = Path(__file__).resolve().parent
    checks: dict[str, Any] = {}
    expectations: tuple[tuple[str, str, str], ...] = (
        ("provability-fabric", "explain_quality", "ExplainQualityReport.v0"),
        ("scientific-memory", "explain_quality", "ExplainQualityReport.v0"),
        ("certifyedge", "profile_coverage", "ProfileCoverageReport.v0"),
    )
    producer_root = packet_dir / "producer_coverage"

    if producer_root.is_dir():
        for producer_id, filename, schema_name in expectations:
            doc_path = producer_root / producer_id / f"{filename}.json"
            key = f"{producer_id}_{filename}"
            if not doc_path.is_file():
                result.errors.append(
                    f"reproduce-smoke: missing {producer_id} {filename} under producer_coverage/"
                )
                result.valid = False
                checks[key] = {"ok": False, "detail": "missing"}
                continue
            doc = json.loads(doc_path.read_text(encoding="utf-8"))
            schema_errors = validate_instance(doc, schema_name, pcs_root)
            if schema_errors:
                for err in schema_errors:
                    result.errors.append(f"reproduce-smoke {producer_id}: {err}")
                result.valid = False
                checks[key] = {"ok": False, "errors": schema_errors}
            else:
                checks[key] = {
                    "ok": True,
                    "producer_id": doc.get("producer_id", producer_id),
                    "case_id": doc.get("case_id") or doc.get("coverage_id"),
                }
        return checks

    explain_path = packet_dir / "explain_quality.json"
    report_path = packet_dir / "BenchmarkReport.v0.json"
    explain_doc: dict | None = None
    if explain_path.exists():
        explain_doc = json.loads(explain_path.read_text(encoding="utf-8"))
    elif report_path.exists():
        report_data = json.loads(report_path.read_text(encoding="utf-8"))
        explain_doc = (report_data.get("coverage") or {}).get("explain_quality")

    if not explain_doc:
        result.errors.append("reproduce-smoke: explain_quality report missing")
        result.valid = False
        checks["explain_quality_schema"] = {"ok": False, "detail": "missing explain_quality"}
        return checks

    explain_errors = validate_instance(explain_doc, "ExplainQualityReport.v0", pcs_root)
    producer_id = explain_doc.get("producer_id", "unknown")
    if explain_errors:
        for err in explain_errors:
            result.errors.append(f"reproduce-smoke explain_quality: {err}")
        result.valid = False
        checks["explain_quality_schema"] = {
            "ok": False,
            "producer_id": producer_id,
            "errors": explain_errors,
        }
    else:
        checks["explain_quality_schema"] = {
            "ok": True,
            "producer_id": producer_id,
            "case_id": explain_doc.get("case_id"),
        }
    return checks


def _reproduction_report_payload(
    packet_dir: Path,
    checks: dict[str, Any],
    *,
    passed: bool,
) -> dict[str, Any]:
    return {
        "schema_version": "v0",
        "packet_dir": str(packet_dir.resolve()),
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "checks": checks,
    }


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
