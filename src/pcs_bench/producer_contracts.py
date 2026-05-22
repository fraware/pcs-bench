"""Producer contract matrix — implementation reference (see docs/producers.md)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from pcs_bench.config import BenchConfig


@dataclass(frozen=True)
class ProducerContract:
    producer_id: str
    repo_url: str
    native_benchmark_command: str
    native_make_target: str
    expected_output_dir: str
    ingest_rel_path: str
    required_schemas: tuple[str, ...]
    adapter_method: str
    minimum_live_cases: int
    fixture_fallback_dir: str
    release_grade_status: str
    case_search_paths: tuple[str, ...]
    benchmark_profile: str | None = None


PRODUCER_CONTRACTS: tuple[ProducerContract, ...] = (
    ProducerContract(
        producer_id="labtrust-gym",
        repo_url="https://github.com/fraware/LabTrust-Gym",
        native_benchmark_command="labtrust benchmark-reproducibility --pcs-core <pcs-core> --certifyedge-bin <certifyedge> --runs <n> --out <out>",
        native_make_target="pcs-bench-producer",
        expected_output_dir="benchmark_runs/labtrust_reproducibility",
        ingest_rel_path="benchmark_runs/labtrust_reproducibility/pcs_bench_ingest.v0.json",
        required_schemas=(
            "PcsBenchIngest.v0",
            "BenchmarkRun.v0",
            "BenchmarkArtifactRef.v0",
            "benchmark_command_entry",
        ),
        adapter_method="LabTrustAdapter.benchmark_reproducibility",
        minimum_live_cases=1,
        fixture_fallback_dir="labtrust_reproducibility",
        release_grade_status="contract-defined",
        case_search_paths=(
            "benchmarks/labtrust-qc-release",
            "benchmarks/labtrust_reproducibility",
            "benchmarks/labtrust_qc_release",
            "examples/pcs_qc_release/benchmark",
        ),
    ),
    ProducerContract(
        producer_id="certifyedge",
        repo_url="https://github.com/fraware/CertifyEdge",
        native_benchmark_command="certifyedge benchmark certificates --profile tool_use_safety --cases <cases> --out <out>",
        native_make_target="pcs-bench-producer",
        expected_output_dir="benchmark_runs/tool_use_safety",
        ingest_rel_path="benchmark_runs/tool_use_safety/pcs_bench_ingest.v0.json",
        required_schemas=(
            "PcsBenchIngest.v0",
            "CoverageReport.v0",
            "ProfileCoverageReport.v0",
            "BenchmarkArtifactRef.v0",
            "benchmark_command_entry",
        ),
        adapter_method="CertifyEdgeAdapter.benchmark_certificates",
        minimum_live_cases=1,
        fixture_fallback_dir="certifyedge",
        release_grade_status="contract-defined",
        case_search_paths=(
            "benchmarks/certificates/tool_use_safety",
            "benchmarks/tool_use_safety",
            "services/pcs-certificate/benchmarks/certificates/tool_use_safety",
        ),
        benchmark_profile="tool_use_safety",
    ),
    ProducerContract(
        producer_id="provability-fabric",
        repo_url="https://github.com/SentinelOps-CI/provability-fabric",
        native_benchmark_command="pf benchmark admission --cases <cases> --registry <registry> --out <out>",
        native_make_target="pcs-bench-producer",
        expected_output_dir="benchmark_runs/labtrust_admission",
        ingest_rel_path="benchmark_runs/labtrust_admission/pcs_bench_ingest.v0.json",
        required_schemas=(
            "PcsBenchIngest.v0",
            "FailureLocalizationResult.v0",
            "ExplainQualityReport.v0",
            "ProfileCoverageReport.v0",
            "BenchmarkArtifactRef.v0",
            "benchmark_command_entry",
        ),
        adapter_method="ProvabilityFabricAdapter.benchmark_admission",
        minimum_live_cases=1,
        fixture_fallback_dir="provability_fabric",
        release_grade_status="contract-defined",
        case_search_paths=(
            "benchmarks/admission/labtrust_qc_release",
            "benchmarks/labtrust_admission",
            "adapters/pcs/benchmarks/admission/labtrust_qc_release",
        ),
    ),
    ProducerContract(
        producer_id="scientific-memory",
        repo_url="https://github.com/fraware/scientific-memory",
        native_benchmark_command="just pcs-benchmark-rendering CASES=<cases> OUT=<out>",
        native_make_target="pcs-bench-producer",
        expected_output_dir="benchmark_runs/labtrust_rendering",
        ingest_rel_path="benchmark_runs/labtrust_rendering/pcs_bench_ingest.v0.json",
        required_schemas=(
            "PcsBenchIngest.v0",
            "ExplainQualityReport.v0",
            "BenchmarkArtifactRef.v0",
            "benchmark_command_entry",
        ),
        adapter_method="ScientificMemoryAdapter.benchmark_rendering",
        minimum_live_cases=1,
        fixture_fallback_dir="scientific_memory",
        release_grade_status="contract-defined",
        case_search_paths=(
            "benchmarks/rendering/labtrust_qc_release",
            "benchmarks/labtrust_rendering",
            "pipeline/benchmarks/rendering/labtrust_qc_release",
        ),
    ),
)

_CONTRACT_BY_ID: dict[str, ProducerContract] = {c.producer_id: c for c in PRODUCER_CONTRACTS}


def contract_for(producer_id: str) -> ProducerContract | None:
    return _CONTRACT_BY_ID.get(producer_id)


def repo_for_contract(cfg: BenchConfig, contract: ProducerContract) -> Path:
    mapping: dict[str, Callable[[BenchConfig], Path]] = {
        "labtrust-gym": lambda c: c.repos.labtrust,
        "certifyedge": lambda c: c.repos.certifyedge,
        "provability-fabric": lambda c: c.repos.provability_fabric,
        "scientific-memory": lambda c: c.repos.scientific_memory,
    }
    return mapping[contract.producer_id](cfg)


def resolve_first_existing(repo: Path, candidates: tuple[str, ...]) -> tuple[Path | None, str | None]:
    """Return (resolved path, candidate string) for the first existing directory under repo."""
    for rel in candidates:
        candidate = repo / rel
        if candidate.is_dir():
            return candidate.resolve(), rel
    return None, None


def rel_path_under_repo(path: Path, repo: Path) -> str:
    """Stable relative path for logging when repo may be configured as `../Repo`."""
    repo_resolved = repo.resolve()
    try:
        return str(path.resolve().relative_to(repo_resolved))
    except ValueError:
        return str(path.resolve())


def resolve_pf_registry(repo: Path, *, pcs_core: Path | None = None) -> Path | None:
    """Resolve PF admission registry (matches scripts/pcs-bench-producer.sh precedence)."""
    candidates: list[Path] = []
    if pcs_core and pcs_core.is_dir():
        candidates.append(pcs_core / "examples" / "artifact_registry.valid.json")
    candidates.extend(
        repo / rel
        for rel in (
            "profiles/registry.json",
            "registry.json",
            "tests/pcs/fixtures/labtrust-release/artifact_registry.json",
        )
    )
    for path in candidates:
        if path.is_file():
            return path.resolve()
    return None


def resolve_native_producer_target(repo: Path, contract: ProducerContract) -> tuple[bool, str]:
    """Return whether the repo exposes the canonical pcs-bench producer Make/script target."""
    makefile = repo / "Makefile"
    if makefile.is_file():
        text = makefile.read_text(encoding="utf-8", errors="replace")
        if f"{contract.native_make_target}:" in text or f"{contract.native_make_target} " in text:
            return True, f"make {contract.native_make_target}"
    script_candidates = {
        "labtrust-gym": ("scripts/pcs_bench_producer.py", "scripts/pcs_bench_producer.ps1"),
        "provability-fabric": ("scripts/pcs-bench-producer.sh", "scripts/pcs-bench-producer.ps1"),
        "scientific-memory": ("scripts/run_pcs_bench_producer_gate.py",),
        "certifyedge": (),
    }
    for rel in script_candidates.get(contract.producer_id, ()):
        if (repo / rel).is_file():
            return True, rel
    return False, f"missing make {contract.native_make_target}"
