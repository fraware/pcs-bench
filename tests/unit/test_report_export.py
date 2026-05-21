"""Report export and pcs-core metrics contract tests."""

from pathlib import Path


from pcs_bench.report_export import (
    export_metrics_for_pcs_core,
    metrics_contract,
    to_benchmark_report_v0_dict,
)
from pcs_bench.schemas import BenchmarkReport, MetricSummary


def _pcs_core() -> Path:
    root = Path(__file__).resolve().parents[2]
    candidate = root.parent / "pcs-core"
    if (candidate / "schemas").is_dir():
        return candidate
    return root / "src" / "pcs_bench"


def test_metrics_contract_is_array():
    assert metrics_contract(_pcs_core()) == "metrics_array"


def test_export_metrics_never_uses_object():
    report = BenchmarkReport(
        metric_summaries=[
            MetricSummary(name="failure_localization_accuracy", score=0.9, applicability="measured")
        ]
    )
    block = export_metrics_for_pcs_core(report, _pcs_core())
    assert isinstance(block["metrics"], list)
    assert "failure_localization_accuracy" in block["metrics"]
    assert isinstance(block["metric_summaries"], list)


def test_to_benchmark_report_v0_dict_rejects_legacy_metrics_object_shape():
    report = BenchmarkReport(
        metric_summaries=[
            MetricSummary(name="registry_coverage_score", score=1.0, applicability="measured")
        ]
    )
    data = to_benchmark_report_v0_dict(report, pcs_core_path=_pcs_core())
    assert isinstance(data["metrics"], list)
    assert not isinstance(data.get("metrics"), dict)
