"""Unit tests for case and suite loading."""

from pathlib import Path

import pytest

from pcs_bench.cases import load_case
from pcs_bench.errors import CaseNotFoundError
from pcs_bench.suites import load_suite, load_suite_cases


BENCH_ROOT = Path(__file__).resolve().parents[2]
LABTRUST_SUITE = BENCH_ROOT / "benchmarks" / "labtrust_qc_release"


def test_load_labtrust_suite():
    suite = load_suite(LABTRUST_SUITE)
    assert suite.suite_id == "labtrust-qc-release-v0"
    assert suite.workflow_id == "hospital_lab.qc_release"
    assert len(suite.cases) == 9


def test_load_suite_cases():
    suite = load_suite(LABTRUST_SUITE)
    cases = load_suite_cases(LABTRUST_SUITE, suite)
    assert len(cases) == 9
    case_ids = [c[0] for c in cases]
    assert "labtrust-valid-release-v0" in case_ids


def test_load_case_fields():
    suite = load_suite(LABTRUST_SUITE)
    _, path, case = load_suite_cases(LABTRUST_SUITE, suite)[1]
    assert case.case_id == "labtrust-trace-hash-tamper-v0"
    assert case.expected_status == "failed"
    assert case.expected_system_outcome == "rejected"
    assert case.expected_failure_code == "trace_hash_mismatch"


def test_missing_case_raises():
    with pytest.raises(CaseNotFoundError):
        load_case(Path("/nonexistent/benchmark_case.v0.json"))
