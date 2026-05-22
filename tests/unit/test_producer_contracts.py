"""Producer contract path resolution."""

from __future__ import annotations

from pathlib import Path

from pcs_bench.producer_contracts import (
    contract_for,
    resolve_native_producer_target,
    resolve_pf_registry,
)


def test_labtrust_case_path_includes_examples() -> None:
    contract = contract_for("labtrust-gym")
    assert contract is not None
    assert "examples/pcs_qc_release/benchmark" in contract.case_search_paths


def test_resolve_pf_registry_prefers_pcs_core_example(tmp_path: Path) -> None:
    repo = tmp_path / "pf"
    repo.mkdir()
    pcs_core = tmp_path / "pcs-core"
    (pcs_core / "examples").mkdir(parents=True)
    registry = pcs_core / "examples" / "artifact_registry.valid.json"
    registry.write_text("{}", encoding="utf-8")
    resolved = resolve_pf_registry(repo, pcs_core=pcs_core)
    assert resolved == registry.resolve()


def test_resolve_native_producer_target_makefile(tmp_path: Path) -> None:
    contract = contract_for("certifyedge")
    assert contract is not None
    repo = tmp_path / "ce"
    repo.mkdir()
    (repo / "Makefile").write_text("pcs-bench-producer:\n\ttrue\n", encoding="utf-8")
    ok, detail = resolve_native_producer_target(repo, contract)
    assert ok is True
    assert "make pcs-bench-producer" in detail
