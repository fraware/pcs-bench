"""Run producer-native benchmarks and ingest PcsBenchIngest.v0 for gate aggregation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from pcs_bench.adapters.certifyedge import CertifyEdgeAdapter
from pcs_bench.adapters.labtrust import LabTrustAdapter
from pcs_bench.adapters.provability_fabric import ProvabilityFabricAdapter
from pcs_bench.adapters.scientific_memory import ScientificMemoryAdapter
from pcs_bench.config import BenchConfig
from pcs_bench.producer_fixtures import PRODUCER_FIXTURE_DIRS, fixture_ingest_path
from pcs_bench.producer_ingest import ingest_producer_output, merge_benchmark_reports
from pcs_bench.reports import load_report, save_report
from pcs_bench.schemas import BenchmarkReport


@dataclass
class ProducerBenchmarkSpec:
    producer: str
    ingest_rel_path: str
    label: str


PRODUCER_BENCHMARKS: tuple[ProducerBenchmarkSpec, ...] = (
    ProducerBenchmarkSpec(
        producer="labtrust-gym",
        ingest_rel_path="benchmark_runs/labtrust_reproducibility/pcs_bench_ingest.v0.json",
        label="LabTrust reproducibility benchmark",
    ),
    ProducerBenchmarkSpec(
        producer="certifyedge",
        ingest_rel_path="benchmark_runs/tool_use_safety/pcs_bench_ingest.v0.json",
        label="CertifyEdge certificate benchmark",
    ),
    ProducerBenchmarkSpec(
        producer="provability-fabric",
        ingest_rel_path="benchmark_runs/labtrust_admission/pcs_bench_ingest.v0.json",
        label="Provability Fabric admission benchmark",
    ),
    ProducerBenchmarkSpec(
        producer="scientific-memory",
        ingest_rel_path="benchmark_runs/labtrust_rendering/pcs_bench_ingest.v0.json",
        label="Scientific Memory rendering benchmark",
    ),
)


@dataclass
class ProducerGateResult:
    reports: list[BenchmarkReport] = field(default_factory=list)
    normalized_paths: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _embedded_fixture_ingest(producer: str) -> Path | None:
    for producer_id, dirname in PRODUCER_FIXTURE_DIRS:
        if producer_id == producer:
            path = fixture_ingest_path(dirname)
            return path if path.is_file() else None
    return None


def _repo_for_producer(cfg: BenchConfig, producer: str) -> Path:
    mapping = {
        "labtrust-gym": cfg.repos.labtrust,
        "certifyedge": cfg.repos.certifyedge,
        "provability-fabric": cfg.repos.provability_fabric,
        "scientific-memory": cfg.repos.scientific_memory,
    }
    return mapping[producer]


def run_producer_benchmark(
    cfg: BenchConfig,
    spec: ProducerBenchmarkSpec,
    *,
    scratch_dir: Path,
) -> Path | None:
    """Run a producer benchmark CLI when available; return ingest file path."""
    repo = _repo_for_producer(cfg, spec.producer)
    if not repo.is_dir():
        return None

    out_dir = scratch_dir / spec.producer.replace("-", "_")
    out_dir.mkdir(parents=True, exist_ok=True)
    ingest_path = repo / spec.ingest_rel_path

    if spec.producer == "labtrust-gym":
        adapter = LabTrustAdapter(repo, cfg)
        adapter.benchmark_reproducibility(1, out_dir)
    elif spec.producer == "certifyedge":
        adapter = CertifyEdgeAdapter(repo, cfg)
        cases = repo / "benchmarks" / "tool_use_safety"
        if cases.is_dir():
            adapter.benchmark_certificates("tool_use_safety", cases, out_dir)
    elif spec.producer == "provability-fabric":
        adapter = ProvabilityFabricAdapter(repo, cfg)
        cases = repo / "benchmarks" / "labtrust_admission"
        registry = repo / "profiles" / "registry.json"
        if not registry.exists():
            registry = repo / "registry.json"
        if cases.is_dir() and registry.exists():
            adapter.benchmark_admission(cases, registry, out_dir)
    elif spec.producer == "scientific-memory":
        adapter = ScientificMemoryAdapter(repo, cfg)
        cases = repo / "benchmarks" / "labtrust_rendering"
        if cases.is_dir():
            adapter.benchmark_rendering(cases, out_dir)

    if ingest_path.is_file():
        return ingest_path

    generated = out_dir / "pcs_bench_ingest.v0.json"
    if generated.is_file():
        return generated
    return None


def collect_producer_ingests(
    cfg: BenchConfig,
    *,
    scratch_dir: Path,
    run_benchmarks: bool = True,
    use_fixture_fallback: bool = False,
) -> ProducerGateResult:
    """Run producer benchmarks (optional) and ingest all PcsBenchIngest.v0 files."""
    result = ProducerGateResult()
    scratch_dir.mkdir(parents=True, exist_ok=True)

    for spec in PRODUCER_BENCHMARKS:
        repo = _repo_for_producer(cfg, spec.producer)
        ingest_path: Path | None = None

        if ingest_path is None and run_benchmarks and repo.is_dir():
            ingest_path = run_producer_benchmark(cfg, spec, scratch_dir=scratch_dir)

        if ingest_path is None:
            candidate = repo / spec.ingest_rel_path
            if candidate.is_file():
                ingest_path = candidate

        if ingest_path is None and use_fixture_fallback:
            ingest_path = _embedded_fixture_ingest(spec.producer)

        if ingest_path is None:
            result.errors.append(
                f"Missing PcsBenchIngest.v0 for {spec.producer} "
                f"(expected {spec.ingest_rel_path} under {repo})"
            )
            continue

        normalized = scratch_dir / f"{spec.producer}.normalized.json"
        try:
            report = ingest_producer_output(
                spec.producer,
                ingest_path,
                normalized,
                pcs_core_path=cfg.repos.pcs_core,
            )
        except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
            fixture_path = (
                _embedded_fixture_ingest(spec.producer) if use_fixture_fallback else None
            )
            if fixture_path is not None and fixture_path != ingest_path:
                try:
                    report = ingest_producer_output(
                        spec.producer,
                        fixture_path,
                        normalized,
                        pcs_core_path=cfg.repos.pcs_core,
                    )
                except (ValueError, FileNotFoundError, json.JSONDecodeError) as fixture_exc:
                    result.errors.append(f"{spec.producer}: {exc}; fixture fallback: {fixture_exc}")
                    continue
            else:
                result.errors.append(f"{spec.producer}: {exc}")
                continue

        result.reports.append(report)
        result.normalized_paths.append(normalized)

    return result


def finalize_merged_gate_report(merged: BenchmarkReport) -> None:
    """Recompute harness metrics on the combined run set without wiping producer coverage."""
    from pcs_bench.metrics import apply_metrics_to_report, compute_all_metrics

    summaries = compute_all_metrics(merged.runs)
    apply_metrics_to_report(merged, summaries)

    pcs_coverage_keys = {
        "registry",
        "formal_checks",
        "scientific_memory",
        "release_reproducibility",
        "certificate_completeness",
        "explain_quality",
        "profile_coverage",
    }
    if not pcs_coverage_keys.intersection(merged.coverage):
        from pcs_bench.coverage import apply_coverage_to_report

        apply_coverage_to_report(merged)
    else:
        from pcs_bench.coverage import compute_coverage

        merged.coverage["harness_aggregates"] = compute_coverage(merged)

    if merged.summary.get("live_cases", 0) == 0:
        merged.summary["evidence_grade"] = "developer"
        merged.summary["execution_mode"] = "simulate"


def aggregate_gate_report(
    cfg: BenchConfig,
    bench_report_path: Path,
    *,
    scratch_dir: Path,
    run_producer_benchmarks: bool,
    out_path: Path,
    require_all_producers: bool = True,
    use_fixture_fallback: bool = False,
) -> list[str]:
    """Merge producer ingests with pcs-bench run report and write aggregate output."""
    errors: list[str] = []
    producer_result = collect_producer_ingests(
        cfg,
        scratch_dir=scratch_dir,
        run_benchmarks=run_producer_benchmarks,
        use_fixture_fallback=use_fixture_fallback,
    )
    errors.extend(producer_result.errors)

    if require_all_producers and len(producer_result.reports) < len(PRODUCER_BENCHMARKS):
        errors.append(
            f"Expected {len(PRODUCER_BENCHMARKS)} producer ingests, got {len(producer_result.reports)}"
        )

    reports: list[BenchmarkReport] = list(producer_result.reports)
    if bench_report_path.is_file():
        reports.append(load_report(bench_report_path))

    if not reports:
        errors.append("No benchmark reports available to aggregate")
        return errors

    merged = merge_benchmark_reports(reports, suite_id="all")
    merged.summary["producer_reports_merged"] = len(producer_result.reports)
    merged.summary["producer_ingest_errors"] = len(producer_result.errors)
    finalize_merged_gate_report(merged)
    save_report(merged, out_path, pcs_core_path=cfg.repos.pcs_core)
    return errors
