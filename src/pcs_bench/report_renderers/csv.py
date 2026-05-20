"""CSV summary renderer."""

from __future__ import annotations

import csv
import io

from pcs_bench.schemas import BenchmarkReport


def render_csv(report: BenchmarkReport) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)

    writer.writerow(["section", "key", "value"])
    writer.writerow(["report", "report_id", report.report_id])
    writer.writerow(["report", "suite_id", report.benchmark_suite_id])
    writer.writerow(["report", "started_at", report.started_at])
    writer.writerow(["report", "completed_at", report.completed_at or ""])

    if report.metric_summaries:
        for summary in sorted(report.metric_summaries, key=lambda s: s.name):
            score_val = "" if summary.score is None else f"{summary.score:.4f}"
            writer.writerow(
                ["metric", summary.name, score_val, summary.applicability, summary.reason or ""]
            )
    else:
        for name, score in sorted(report.metrics.items()):
            if isinstance(score, (int, float)):
                writer.writerow(["metric", name, f"{score:.4f}", "measured", ""])

    writer.writerow([])
    writer.writerow(
        [
            "case_id",
            "suite_id",
            "passed",
            "expected_status",
            "observed_status",
            "expected_failure_code",
            "observed_failure_code",
            "expected_component",
            "observed_component",
            "duration_ms",
        ]
    )
    for r in report.runs:
        writer.writerow(
            [
                r.case_id,
                r.suite_id,
                r.passed,
                r.expected_status,
                r.observed_status,
                r.expected_failure_code or "",
                r.observed_failure_code or "",
                r.expected_responsible_component or "",
                r.observed_responsible_component or "",
                r.duration_ms,
            ]
        )

    return buf.getvalue()
