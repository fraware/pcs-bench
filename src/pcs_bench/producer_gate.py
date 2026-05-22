"""Run producer-native benchmarks and ingest PcsBenchIngest.v0 for gate aggregation."""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from pcs_bench.adapters.certifyedge import CertifyEdgeAdapter
from pcs_bench.adapters.labtrust import LabTrustAdapter
from pcs_bench.adapters.provability_fabric import ProvabilityFabricAdapter
from pcs_bench.adapters.scientific_memory import ScientificMemoryAdapter
from pcs_bench.config import BenchConfig
from pcs_bench.producer_contracts import (
    PRODUCER_CONTRACTS,
    ProducerContract,
    contract_for,
    repo_for_contract,
    rel_path_under_repo,
    resolve_first_existing,
    resolve_pf_registry,
)
from pcs_bench.producer_fixtures import PRODUCER_FIXTURE_DIRS, fixture_ingest_path
from pcs_bench.producer_artifacts import write_producer_gate_result
from pcs_bench.producer_ingest import (
    ProducerMergeEntry,
    ingest_producer_output,
    merge_benchmark_reports,
    write_producer_merge_manifest,
)
from pcs_bench.reports import load_report, save_report
from pcs_bench.schemas import BenchmarkReport


@dataclass
class ProducerBenchmarkSpec:
    producer: str
    ingest_rel_path: str
    label: str


def _spec_from_contract(contract: ProducerContract) -> ProducerBenchmarkSpec:
    return ProducerBenchmarkSpec(
        producer=contract.producer_id,
        ingest_rel_path=contract.ingest_rel_path,
        label=f"{contract.producer_id} benchmark",
    )


PRODUCER_BENCHMARKS: tuple[ProducerBenchmarkSpec, ...] = tuple(
    _spec_from_contract(c) for c in PRODUCER_CONTRACTS
)


@dataclass
class ProducerBenchmarkRunOutcome:
    ingest_path: Path | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ProducerGateResult:
    reports: list[BenchmarkReport] = field(default_factory=list)
    normalized_paths: list[Path] = field(default_factory=list)
    merge_entries: list[ProducerMergeEntry] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _log_path_selection(producer: str, kind: str, selected: str) -> None:
    print(f"[producer-gate] {producer}: selected {kind}={selected}", file=sys.stderr)


def _embedded_fixture_ingest(producer: str) -> Path | None:
    for producer_id, dirname in PRODUCER_FIXTURE_DIRS:
        if producer_id == producer:
            path = fixture_ingest_path(dirname)
            return path if path.is_file() else None
    return None


def _repo_for_producer(cfg: BenchConfig, producer: str) -> Path:
    contract = contract_for(producer)
    if contract:
        return repo_for_contract(cfg, contract)
    mapping = {
        "labtrust-gym": cfg.repos.labtrust,
        "certifyedge": cfg.repos.certifyedge,
        "provability-fabric": cfg.repos.provability_fabric,
        "scientific-memory": cfg.repos.scientific_memory,
    }
    return mapping[producer]


def resolve_canonical_ingest_path(repo: Path, contract: ProducerContract) -> Path:
    """Explicit canonical ingest location under the producer repo."""
    return (repo / contract.ingest_rel_path).resolve()


def resolve_benchmark_output_dir(repo: Path, contract: ProducerContract) -> Path:
    """Explicit benchmark_runs output directory for producer-native CLI."""
    return (repo / contract.expected_output_dir).resolve()


def resolve_cases_dir(repo: Path, contract: ProducerContract) -> tuple[Path | None, str | None]:
    """First matching benchmark case directory from the contract search list."""
    return resolve_first_existing(repo, contract.case_search_paths)


def _discover_ingest_path(
    repo: Path,
    contract: ProducerContract,
    *,
    canonical_ingest: Path,
    canonical_output: Path,
    scratch_out: Path,
) -> Path | None:
    """Resolve ingest from canonical, scratch, or output-dir locations."""
    candidates: list[tuple[str, Path]] = [
        ("canonical", canonical_ingest),
        ("scratch", scratch_out / "pcs_bench_ingest.v0.json"),
        ("output_dir", canonical_output / "pcs_bench_ingest.v0.json"),
    ]
    for label, path in candidates:
        if path.is_file():
            _log_path_selection(
                contract.producer_id, "ingest", f"{label}:{rel_path_under_repo(path, repo)}"
            )
            return path
    return None


def _promote_ingest_to_canonical(
    producer: str,
    source: Path,
    canonical: Path,
    repo: Path,
) -> Path:
    """Copy a generated ingest to the contract canonical path when possible."""
    if not source.is_file() or source.resolve() == canonical.resolve():
        return source
    canonical.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, canonical)
    _log_path_selection(producer, "promoted_ingest", rel_path_under_repo(canonical, repo))
    return canonical


def _merge_entry_from_ingest(
    producer: str,
    ingest_path: Path,
    normalized_path: Path,
) -> ProducerMergeEntry:
    data = json.loads(ingest_path.read_text(encoding="utf-8"))
    return ProducerMergeEntry(
        producer_id=producer,
        suite_id=str(data.get("suite_id", producer)),
        source_repo=str(data.get("source_repo", "")),
        source_commit=str(data.get("source_commit", "")),
        ingest_digest=str(data.get("signature_or_digest", "")),
        ingest_path=str(ingest_path.resolve()),
        normalized_path=str(normalized_path.resolve()),
    )


def run_producer_benchmark(
    cfg: BenchConfig,
    spec: ProducerBenchmarkSpec,
    *,
    scratch_dir: Path,
) -> ProducerBenchmarkRunOutcome:
    """Run a producer benchmark CLI when available; return ingest path and diagnostics."""
    outcome = ProducerBenchmarkRunOutcome()
    contract = contract_for(spec.producer)
    if not contract:
        outcome.errors.append(f"no contract for {spec.producer}")
        return outcome

    repo = _repo_for_producer(cfg, spec.producer)
    if not repo.is_dir():
        outcome.errors.append(f"repo not found: {repo}")
        return outcome

    scratch_out = scratch_dir / spec.producer.replace("-", "_")
    scratch_out.mkdir(parents=True, exist_ok=True)
    canonical_ingest = resolve_canonical_ingest_path(repo, contract)
    canonical_output = resolve_benchmark_output_dir(repo, contract)
    canonical_output.mkdir(parents=True, exist_ok=True)
    _log_path_selection(
        spec.producer,
        "canonical_output_dir",
        rel_path_under_repo(canonical_output, repo),
    )

    if spec.producer == "labtrust-gym":
        adapter = LabTrustAdapter(repo, cfg)
        result = adapter.benchmark_reproducibility(1, canonical_output)
        if result.exit_code != 0:
            outcome.warnings.append(
                f"labtrust benchmark-reproducibility exit_code={result.exit_code}"
            )
        cases_path, cases_rel = resolve_cases_dir(repo, contract)
        if cases_path:
            _log_path_selection(spec.producer, "cases_dir", cases_rel or str(cases_path))
    elif spec.producer == "certifyedge":
        cases_path, cases_rel = resolve_cases_dir(repo, contract)
        if not cases_path:
            outcome.errors.append(
                f"no benchmark cases directory under {repo} "
                f"(searched: {', '.join(contract.case_search_paths)})"
            )
        else:
            _log_path_selection(spec.producer, "cases_dir", cases_rel or str(cases_path))
            adapter = CertifyEdgeAdapter(repo, cfg)
            profile = contract.benchmark_profile or "tool_use_safety"
            result = adapter.benchmark_certificates(profile, cases_path, canonical_output)
            if result.exit_code != 0:
                outcome.warnings.append(
                    f"certifyedge benchmark exit_code={result.exit_code}"
                )
    elif spec.producer == "provability-fabric":
        cases_path, cases_rel = resolve_cases_dir(repo, contract)
        registry = resolve_pf_registry(repo)
        if not cases_path:
            outcome.errors.append(
                f"no benchmark cases directory under {repo} "
                f"(searched: {', '.join(contract.case_search_paths)})"
            )
        elif not registry:
            outcome.errors.append("no profiles/registry.json or registry.json under repo")
        else:
            _log_path_selection(spec.producer, "cases_dir", cases_rel or str(cases_path))
            adapter = ProvabilityFabricAdapter(repo, cfg)
            result = adapter.benchmark_admission(cases_path, registry, canonical_output)
            if result.exit_code != 0:
                outcome.warnings.append(f"pf benchmark admission exit_code={result.exit_code}")
    elif spec.producer == "scientific-memory":
        cases_path, cases_rel = resolve_cases_dir(repo, contract)
        if not cases_path:
            outcome.errors.append(
                f"no benchmark cases directory under {repo} "
                f"(searched: {', '.join(contract.case_search_paths)})"
            )
        else:
            _log_path_selection(spec.producer, "cases_dir", cases_rel or str(cases_path))
            adapter = ScientificMemoryAdapter(repo, cfg)
            result = adapter.benchmark_rendering(cases_path, canonical_output)
            if result.exit_code != 0:
                outcome.warnings.append(
                    f"scientific-memory benchmark exit_code={result.exit_code}"
                )

    discovered = _discover_ingest_path(
        repo,
        contract,
        canonical_ingest=canonical_ingest,
        canonical_output=canonical_output,
        scratch_out=scratch_out,
    )
    if discovered is None:
        outcome.errors.append(
            f"benchmark completed but no pcs_bench_ingest.v0.json under "
            f"{rel_path_under_repo(canonical_ingest, repo)} or "
            f"{rel_path_under_repo(canonical_output, repo)}"
        )
        return outcome

    if discovered != canonical_ingest:
        outcome.ingest_path = _promote_ingest_to_canonical(
            spec.producer, discovered, canonical_ingest, repo
        )
    else:
        outcome.ingest_path = discovered

    return outcome


def collect_producer_ingests(
    cfg: BenchConfig,
    *,
    scratch_dir: Path,
    run_benchmarks: bool = True,
    use_fixture_fallback: bool = False,
    release_grade: bool = False,
) -> ProducerGateResult:
    """Run producer benchmarks (optional) and ingest all PcsBenchIngest.v0 files."""
    result = ProducerGateResult()
    scratch_dir.mkdir(parents=True, exist_ok=True)
    strict = release_grade and not use_fixture_fallback

    for spec in PRODUCER_BENCHMARKS:
        repo = _repo_for_producer(cfg, spec.producer)
        ingest_path: Path | None = None
        from_repo = repo.is_dir()

        benchmark_errors: list[str] = []
        try_live_benchmark = run_benchmarks and from_repo and not use_fixture_fallback
        if try_live_benchmark:
            run_outcome = run_producer_benchmark(cfg, spec, scratch_dir=scratch_dir)
            benchmark_errors = list(run_outcome.errors)
            for warning in run_outcome.warnings:
                print(
                    f"[producer-gate] {spec.producer}: warning: {warning}",
                    file=sys.stderr,
                )
            if ingest_path is None:
                ingest_path = run_outcome.ingest_path

        if ingest_path is None:
            candidate = repo / spec.ingest_rel_path
            if candidate.is_file():
                ingest_path = candidate

        if ingest_path is None and use_fixture_fallback:
            ingest_path = _embedded_fixture_ingest(spec.producer)
            from_repo = False
            benchmark_errors = []

        if benchmark_errors and (strict or not use_fixture_fallback):
            result.errors.extend(f"{spec.producer}: {msg}" for msg in benchmark_errors)

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
                release_grade=strict,
                producer_repo=repo if from_repo else None,
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
                        release_grade=False,
                        producer_repo=None,
                    )
                    ingest_path = fixture_path
                    from_repo = False
                except (ValueError, FileNotFoundError, json.JSONDecodeError) as fixture_exc:
                    result.errors.append(
                        f"{spec.producer}: {exc}; fixture fallback: {fixture_exc}"
                    )
                    continue
            else:
                result.errors.append(f"{spec.producer}: {exc}")
                continue

        result.reports.append(report)
        result.normalized_paths.append(normalized)
        result.merge_entries.append(
            _merge_entry_from_ingest(spec.producer, ingest_path, normalized)
        )

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
    release_grade: bool = False,
) -> list[str]:
    """Merge producer ingests with pcs-bench run report and write aggregate output."""
    errors: list[str] = []
    producer_result = collect_producer_ingests(
        cfg,
        scratch_dir=scratch_dir,
        run_benchmarks=run_producer_benchmarks,
        use_fixture_fallback=use_fixture_fallback,
        release_grade=release_grade,
    )
    errors.extend(producer_result.errors)

    if require_all_producers and len(producer_result.reports) < len(PRODUCER_BENCHMARKS):
        errors.append(
            f"Expected {len(PRODUCER_BENCHMARKS)} producer ingests, "
            f"got {len(producer_result.reports)}"
        )

    reports: list[BenchmarkReport] = list(producer_result.reports)
    if bench_report_path.is_file():
        reports.append(load_report(bench_report_path))

    if not reports:
        errors.append("No benchmark reports available to aggregate")
        return errors

    merged = merge_benchmark_reports(
        reports,
        suite_id="all",
        producer_entries=producer_result.merge_entries,
    )
    merged.summary["producer_reports_merged"] = len(producer_result.reports)
    merged.summary["producer_ingest_errors"] = len(producer_result.errors)
    finalize_merged_gate_report(merged)
    save_report(merged, out_path, pcs_core_path=cfg.repos.pcs_core)
    if producer_result.merge_entries:
        manifest = write_producer_merge_manifest(out_path, producer_result.merge_entries)
        print(f"[producer-gate] wrote merge manifest {manifest}", file=sys.stderr)
    gate_result = write_producer_gate_result(
        out_path,
        errors=errors,
        merge_entries=producer_result.merge_entries,
        release_grade=release_grade,
        use_fixture_fallback=use_fixture_fallback,
    )
    print(f"[producer-gate] wrote gate result {gate_result}", file=sys.stderr)
    return errors
