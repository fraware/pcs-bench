"""Unit tests for metrics."""

from pcs_bench.metrics import (
    compute_failure_localization_accuracy,
    compute_formal_check_coverage_score,
    compute_release_reproducibility_score,
    compute_repair_hint_quality_score,
)
from pcs_bench.schemas import BenchmarkRun


def _run(case_id: str, expected_status: str, observed_status: str, **kwargs) -> BenchmarkRun:
    return BenchmarkRun(
        run_id="r1",
        case_id=case_id,
        suite_id="s1",
        expected_status=expected_status,
        observed_status=observed_status,
        passed=kwargs.get("passed", False),
        expected_responsible_component=kwargs.get("expected_component"),
        observed_responsible_component=kwargs.get("observed_component"),
        expected_failure_code=kwargs.get("expected_failure_code"),
        observed_failure_code=kwargs.get("observed_failure_code"),
        observed_repair_hint=kwargs.get("repair_hint"),
    )


def test_release_reproducibility_all_pass():
    runs = [
        _run("v1", "Admitted", "Admitted", passed=True),
        _run("v2", "Admitted", "Admitted", passed=True),
    ]
    m = compute_release_reproducibility_score(runs)
    assert m.score == 1.0


def test_failure_localization_accuracy():
    runs = [
        _run(
            "i1",
            "Rejected",
            "Rejected",
            expected_component="runtime_producer",
            observed_component="runtime_producer",
        ),
        _run(
            "i2",
            "Rejected",
            "Rejected",
            expected_component="verifier",
            observed_component="runtime_producer",
        ),
    ]
    m = compute_failure_localization_accuracy(runs)
    assert m.score == 0.5
    assert m.numerator == 1
    assert m.denominator == 2


def test_formal_check_insufficient_without_formal_cases():
    runs = [
        _run("t1", "Admitted", "Admitted", passed=True),
    ]
    m = compute_formal_check_coverage_score(runs)
    assert m.score is None
    assert m.applicability == "insufficient_cases"


def test_repair_hint_quality():
    runs = [
        _run(
            "i1",
            "Rejected",
            "Rejected",
            expected_failure_code="x",
            observed_failure_code="x",
            observed_component="runtime_producer",
            repair_hint="regenerate",
        ),
    ]
    m = compute_repair_hint_quality_score(runs)
    assert m.score == 1.0
