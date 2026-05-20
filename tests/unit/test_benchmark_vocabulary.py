"""Vocabulary normalization and case policy tests."""

from pcs_bench.benchmark_vocabulary import (
    BENCHMARK_FAILED,
    BENCHMARK_PASSED,
    SYSTEM_ADMITTED,
    SYSTEM_REJECTED,
    normalize_legacy_case_payload,
)


def test_normalize_legacy_admitted_split():
    raw = {
        "expected_status": "Admitted",
        "input_artifacts": {"release_dir": "input/"},
    }
    out = normalize_legacy_case_payload(raw)
    assert out["expected_status"] == BENCHMARK_PASSED
    assert out["expected_system_outcome"] == SYSTEM_ADMITTED
    assert out["input_artifacts"]["release_directory"] == "input/"


def test_normalize_legacy_rejected_split():
    raw = {"expected_status": "Rejected"}
    out = normalize_legacy_case_payload(raw)
    assert out["expected_status"] == BENCHMARK_FAILED
    assert out["expected_system_outcome"] == SYSTEM_REJECTED


def test_normalize_case_kind_alias():
    raw = {
        "expected_status": "failed",
        "case_kind": "valid_tool_use",
    }
    out = normalize_legacy_case_payload(raw)
    assert out["case_kind"] == "valid_release"
