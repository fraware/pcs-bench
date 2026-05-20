"""Suite-level metric and live-execution policy."""

from __future__ import annotations

from pathlib import Path

from pcs_bench.metrics import ALL_METRIC_NAMES, SUITE_ALL_REQUIRED_METRICS
from pcs_bench.suites import load_suite


def collect_suite_policy(
    benchmarks_root: Path,
    suite_names: list[str],
) -> tuple[set[str], set[str], list[str]]:
    """Return (required_metrics, optional_metrics, live_required_suite_ids)."""
    if len(suite_names) > 1 or suite_names == ["all"]:
        return set(SUITE_ALL_REQUIRED_METRICS), set(), []

    required: set[str] = set()
    optional: set[str] = set()
    live_required: list[str] = []

    for suite_name in suite_names:
        suite_dir = benchmarks_root / suite_name
        if not suite_dir.exists():
            continue
        suite = load_suite(suite_dir)
        if suite.required_metrics:
            required.update(suite.required_metrics)
        elif suite.metrics:
            required.update(suite.metrics)
        if suite.optional_metrics:
            optional.update(suite.optional_metrics)
        if suite.live_required_for_release:
            live_required.append(suite.suite_id)

    if not required:
        required = set(ALL_METRIC_NAMES)
    return required, optional, live_required
