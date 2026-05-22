"""Diagnostic checks for producer repo readiness (non-gating)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pcs_bench.adapters.certifyedge import CertifyEdgeAdapter
from pcs_bench.adapters.labtrust import LabTrustAdapter
from pcs_bench.adapters.provability_fabric import ProvabilityFabricAdapter
from pcs_bench.adapters.scientific_memory import ScientificMemoryAdapter
from pcs_bench.adapters.base import AdapterStatus
from pcs_bench.config import BenchConfig
from pcs_bench.ingest_validation import (
    PRODUCER_EMBEDDED_REF_FIELDS,
    validate_ingest_json,
)
from pcs_bench.producer_contracts import (
    PRODUCER_CONTRACTS,
    ProducerContract,
    repo_for_contract,
    resolve_first_existing,
    resolve_pf_registry,
)
from pcs_bench.producer_fixtures import fixture_ingest_path
from pcs_bench.producer_contracts import rel_path_under_repo
from pcs_bench.producer_gate import resolve_benchmark_output_dir, resolve_canonical_ingest_path


@dataclass
class DoctorCheck:
    name: str
    ok: bool
    detail: str


@dataclass
class ProducerDoctorReport:
    producer_id: str
    repo_path: str
    checks: list[DoctorCheck] = field(default_factory=list)
    ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "producer_id": self.producer_id,
            "repo_path": self.repo_path,
            "ready": self.ready,
            "checks": [asdict(c) for c in self.checks],
        }


@dataclass
class ProducerDoctorResult:
    generated_at: str
    producers: list[ProducerDoctorReport] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "v0",
            "generated_at": self.generated_at,
            "producers": [p.to_dict() for p in self.producers],
            "all_ready": all(p.ready for p in self.producers),
        }


def _adapter_for(contract: ProducerContract, repo: Path, cfg: BenchConfig):
    if contract.producer_id == "labtrust-gym":
        return LabTrustAdapter(repo, cfg)
    if contract.producer_id == "certifyedge":
        return CertifyEdgeAdapter(repo, cfg)
    if contract.producer_id == "provability-fabric":
        return ProvabilityFabricAdapter(repo, cfg)
    return ScientificMemoryAdapter(repo, cfg)


def _check_repo_exists(repo: Path) -> DoctorCheck:
    if repo.is_dir():
        return DoctorCheck("repo_exists", True, str(repo.resolve()))
    return DoctorCheck("repo_exists", False, f"not found: {repo}")


def _check_cli_smoke(adapter) -> DoctorCheck:
    status = adapter.run_smoke_check()
    ok = status == AdapterStatus.AVAILABLE
    return DoctorCheck("cli_smoke", ok, status.value)


def _check_cases_dir(repo: Path, contract: ProducerContract) -> DoctorCheck:
    path, rel = resolve_first_existing(repo, contract.case_search_paths)
    if path:
        return DoctorCheck("benchmark_cases_dir", True, rel or str(path))
    return DoctorCheck(
        "benchmark_cases_dir",
        False,
        f"none of {list(contract.case_search_paths)} exist under {repo}",
    )


def _check_output_dir_writable(repo: Path, contract: ProducerContract) -> DoctorCheck:
    repo_resolved = repo.resolve()
    out = resolve_benchmark_output_dir(repo_resolved, contract)
    try:
        out.mkdir(parents=True, exist_ok=True)
        probe = out / ".pcs_bench_doctor_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return DoctorCheck(
            "output_dir_writable", True, rel_path_under_repo(out, repo_resolved)
        )
    except OSError as exc:
        return DoctorCheck("output_dir_writable", False, str(exc))


def _rel_to_repo(path: Path, repo: Path) -> str:
    repo_resolved = repo.resolve()
    try:
        return str(path.resolve().relative_to(repo_resolved))
    except ValueError:
        return str(path.resolve())


def _check_ingest(repo: Path, contract: ProducerContract) -> DoctorCheck:
    ingest = resolve_canonical_ingest_path(repo, contract)
    if ingest.is_file():
        return DoctorCheck("ingest_present", True, _rel_to_repo(ingest, repo))
    scratch_candidate = repo / contract.expected_output_dir / "pcs_bench_ingest.v0.json"
    if scratch_candidate.is_file():
        return DoctorCheck(
            "ingest_present",
            True,
            f"{rel_path_under_repo(scratch_candidate, repo)} (under output dir)",
        )
    return DoctorCheck(
        "ingest_present",
        False,
        f"missing {contract.ingest_rel_path}; run native benchmark to generate",
    )


def _check_ingest_validates(
    repo: Path,
    contract: ProducerContract,
    schema_root: Path,
    *,
    release_grade: bool,
) -> DoctorCheck:
    ingest = resolve_canonical_ingest_path(repo, contract)
    if not ingest.is_file():
        return DoctorCheck("ingest_validates", False, "no ingest file to validate")
    errors = validate_ingest_json(
        ingest,
        schema_root,
        release_grade=release_grade,
        producer_repo=repo,
    )
    if errors:
        return DoctorCheck("ingest_validates", False, "; ".join(errors[:3]))
    grade = "release-grade" if release_grade else "schema"
    return DoctorCheck("ingest_validates", True, f"passed {grade} validation")


def _check_artifact_refs(repo: Path, contract: ProducerContract, schema_root: Path) -> DoctorCheck:
    ingest = resolve_canonical_ingest_path(repo, contract)
    if not ingest.is_file():
        return DoctorCheck("artifact_refs", False, "no ingest")
    data = json.loads(ingest.read_text(encoding="utf-8"))
    fields = PRODUCER_EMBEDDED_REF_FIELDS.get(contract.producer_id, ())
    has_embedded = any(isinstance(data.get(f), list) and data.get(f) for f in fields)
    refs = data.get("artifact_refs")
    if has_embedded and not refs:
        return DoctorCheck("artifact_refs", False, "embedded artifacts require artifact_refs")
    if not refs:
        return DoctorCheck("artifact_refs", True, "not required for this ingest")
    errors = validate_ingest_json(
        ingest,
        schema_root,
        release_grade=True,
        producer_repo=repo,
    )
    sidecar_errors = [e for e in errors if "sidecar file missing" in e]
    if sidecar_errors:
        return DoctorCheck("artifact_refs", False, sidecar_errors[0])
    return DoctorCheck("artifact_refs", True, f"{len(refs)} ref(s) OK")


def _check_native_command(adapter, contract: ProducerContract) -> DoctorCheck:
    status = adapter.run_smoke_check()
    if status != AdapterStatus.AVAILABLE:
        return DoctorCheck("native_command", False, f"CLI unavailable: {status.value}")
    return DoctorCheck("native_command", True, contract.native_benchmark_command[:80] + "...")


def _check_pf_registry(repo: Path, contract: ProducerContract) -> DoctorCheck | None:
    if contract.producer_id != "provability-fabric":
        return None
    registry = resolve_pf_registry(repo)
    if registry:
        return DoctorCheck("pf_registry", True, rel_path_under_repo(registry, repo))
    return DoctorCheck("pf_registry", False, "profiles/registry.json or registry.json missing")


def diagnose_producer(
    cfg: BenchConfig,
    contract: ProducerContract,
    *,
    schema_root: Path,
    release_grade: bool = False,
) -> ProducerDoctorReport:
    repo = repo_for_contract(cfg, contract)
    report = ProducerDoctorReport(producer_id=contract.producer_id, repo_path=str(repo))

    report.checks.append(_check_repo_exists(repo))
    if not report.checks[-1].ok:
        report.ready = False
        return report

    adapter = _adapter_for(contract, repo, cfg)
    report.checks.append(_check_cli_smoke(adapter))
    report.checks.append(_check_native_command(adapter, contract))
    report.checks.append(_check_cases_dir(repo, contract))
    pf_registry = _check_pf_registry(repo, contract)
    if pf_registry:
        report.checks.append(pf_registry)
    report.checks.append(_check_output_dir_writable(repo, contract))
    report.checks.append(_check_ingest(repo, contract))
    report.checks.append(
        _check_ingest_validates(repo, contract, schema_root, release_grade=release_grade)
    )
    report.checks.append(_check_artifact_refs(repo, contract, schema_root))

    fixture = fixture_ingest_path(contract.fixture_fallback_dir)
    report.checks.append(
        DoctorCheck(
            "fixture_fallback",
            fixture.is_file(),
            str(fixture) if fixture.is_file() else "missing embedded fixture",
        )
    )

    report.ready = all(c.ok for c in report.checks if c.name != "fixture_fallback")
    return report


def run_producer_doctor(
    cfg: BenchConfig,
    *,
    schema_root: Path,
    release_grade: bool = False,
) -> ProducerDoctorResult:
    result = ProducerDoctorResult(generated_at=datetime.now(timezone.utc).isoformat())
    for contract in PRODUCER_CONTRACTS:
        result.producers.append(
            diagnose_producer(cfg, contract, schema_root=schema_root, release_grade=release_grade)
        )
    return result
