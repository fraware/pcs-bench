"""Unit tests for fixture simulation."""

from pathlib import Path

from pcs_bench.cases import load_case
from pcs_bench.simulation import simulate_outcome

BENCH_ROOT = Path(__file__).resolve().parents[2]
SUITE = BENCH_ROOT / "benchmarks" / "labtrust_qc_release"


def test_simulate_invalid_case_from_sidecar():
    case_path = SUITE / "invalid" / "trace_hash_tamper" / "benchmark_case.v0.json"
    case = load_case(case_path)
    outcome = simulate_outcome(case, SUITE)
    assert outcome.status == "Rejected"
    assert outcome.failure_code == "trace_hash_mismatch"
    assert outcome.responsible_component == "runtime_producer"
    assert outcome.source == "expected_sidecar"


def test_simulate_valid_case():
    case_path = SUITE / "valid" / "labtrust-valid-release-v0" / "benchmark_case.v0.json"
    case = load_case(case_path)
    outcome = simulate_outcome(case, SUITE)
    assert outcome.status == "Admitted"
