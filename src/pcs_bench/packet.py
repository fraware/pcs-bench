"""Export public benchmark packets for external reviewers."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from pcs_bench.config import BenchConfig
from pcs_bench.report_renderers.csv import render_csv
from pcs_bench.report_renderers.html import render_html
from pcs_bench.report_renderers.markdown import render_markdown
from pcs_bench.reports import load_report
from pcs_bench.schemas import BenchmarkReport


def export_benchmark_packet(
    report_path: Path,
    out_dir: Path,
    config: BenchConfig | None = None,
    *,
    baseline_path: Path | None = None,
) -> Path:
    """Create a self-contained reviewer packet directory."""
    report = load_report(report_path)
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

    (out_dir / "BenchmarkReport.v0.json").write_text(
        json.dumps(report.model_dump(), indent=2, default=str),
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
    benchmarks_root = (config or BenchConfig()).benchmarks_root.resolve()

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
                    "fixture_path": str(dest.relative_to(out_dir)),
                }
            )

    (out_dir / "case_manifest.json").write_text(
        json.dumps(manifest_cases, indent=2),
        encoding="utf-8",
    )

    readme = _reviewer_readme(report, out_dir)
    (out_dir / "README.md").write_text(readme, encoding="utf-8")
    _write_reproduce_script(out_dir)

    meta = {
        "packet_version": "v0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "report_id": report.report_id,
        "digest": report.signature_or_digest,
        "execution_mode": report.summary.get("execution_mode", "unknown"),
    }
    (out_dir / "packet_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return out_dir


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
| `BenchmarkReport.v0.json` | Machine-readable benchmark report |
| `report.md` / `report.html` | Human-readable summaries |
| `summary.csv` | Per-case CSV |
| `cases/` | Fixture inputs used for each case |
| `case_manifest.json` | Case index |
| `reproduce.ps1` / `reproduce.sh` | Re-run simulate benchmark |

## Reproduce

```bash
pip install -e .
python scripts/materialize_fixtures.py
pcs-bench run --suite all --simulate --ci --out reports/repro.json
pcs-bench compare --old BenchmarkReport.v0.json --new reports/repro.json
```

## Verify one valid and one invalid case

1. Pick a passing valid case from `case_manifest.json`
2. Pick a failing invalid case
3. Inspect `cases/<case_id>/expected/` sidecars vs `input_artifacts/`

Digest: `{report.signature_or_digest or "n/a"}`
"""


def _write_reproduce_script(out_dir: Path) -> None:
    sh = """#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
pip install -e ".[dev]" >/dev/null
python scripts/materialize_fixtures.py
pcs-bench run --suite all --simulate --out reports/repro.json
pcs-bench compare --old packets/latest/BenchmarkReport.v0.json --new reports/repro.json
"""
    ps1 = """$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
pip install -e ".[dev]"
python scripts/materialize_fixtures.py
pcs-bench run --suite all --simulate --out reports/repro.json
pcs-bench compare --old packets/latest/BenchmarkReport.v0.json --new reports/repro.json
"""
    (out_dir / "reproduce.sh").write_text(sh, encoding="utf-8")
    (out_dir / "reproduce.ps1").write_text(ps1, encoding="utf-8")
