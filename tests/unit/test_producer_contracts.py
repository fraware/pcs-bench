"""Tests for producer contract path resolution."""

from __future__ import annotations

from pathlib import Path

from pcs_bench.producer_contracts import PRODUCER_CONTRACTS, contract_for, resolve_first_existing


def test_certifyedge_case_search_order(tmp_path: Path) -> None:
    contract = contract_for("certifyedge")
    assert contract is not None
    third = tmp_path / "services/pcs-certificate/benchmarks/certificates/tool_use_safety"
    third.mkdir(parents=True)
    path, rel = resolve_first_existing(tmp_path, contract.case_search_paths)
    assert path is not None
    assert rel == "services/pcs-certificate/benchmarks/certificates/tool_use_safety"


def test_pf_case_search_falls_through(tmp_path: Path) -> None:
    contract = contract_for("provability-fabric")
    assert contract is not None
    fallback = tmp_path / "benchmarks/labtrust_admission"
    fallback.mkdir(parents=True)
    path, rel = resolve_first_existing(tmp_path, contract.case_search_paths)
    assert path == fallback.resolve()
    assert rel == "benchmarks/labtrust_admission"


def test_all_contracts_have_ingest_paths() -> None:
    for contract in PRODUCER_CONTRACTS:
        assert contract.ingest_rel_path.endswith("pcs_bench_ingest.v0.json")
        assert contract.expected_output_dir in contract.ingest_rel_path
