# Producer contract matrix

This document is the source of truth for `producer_contracts.py`, `producer_gate.py`, and `pcs-bench producer-doctor`. Every PCS producer repo must emit `pcs_bench_ingest.v0.json` validated against schemas owned by [pcs-core](https://github.com/SentinelOps-CI/pcs-core).

## Canonical ingest

| Requirement | Rule |
|-------------|------|
| Filename | `pcs_bench_ingest.v0.json` |
| Schema | `PcsBenchIngest.v0` (pcs-core) |
| Embedded objects | `benchmark_runs`, `coverage_reports`, `failure_localization_reports`, `explain_quality_reports`, `profile_coverage_reports`, `commands`, `logs`, `source_repo`, `source_commit`, digest |
| `artifact_refs` | Optional sidecar provenance (`BenchmarkArtifactRef.v0`); never replace embedded objects |
| Native target | `make pcs-bench-producer` (validates via pcs-core + pcs-bench) |

## Release-grade adequacy

`pcs-bench validate-ingest --release-grade` and live `gate --run-producer-benchmarks` (without `--use-producer-fixtures`) require:

| Check | Applies to |
|-------|------------|
| `source_commit` is 40-char hex, not all zeros | all |
| `benchmark_runs` non-empty | all (CertifyEdge may satisfy via non-empty `coverage_reports` + `profile_coverage_reports` only) |
| `commands` non-empty | all |
| `coverage_reports` non-empty | certifyedge |
| `failure_localization_reports` non-empty | provability-fabric |
| `explain_quality_reports` non-empty | provability-fabric, scientific-memory |
| `profile_coverage_reports` non-empty | certifyedge |
| No `execution_kind=simulate` on runs | all with runs |
| `artifact_refs` sidecars exist and digests match embedded objects | when refs present (skipped for pcs-bench golden fixtures) |
| pcs-core schema validation | all |
| `pcs-bench validate-ingest` | all |

Developer / fixture mode (`--use-producer-fixtures`) sets aggregate `evidence_grade: developer` and `fixture_fallback_used: true`. Release-grade gate rejects `--use-producer-fixtures` with `--live`.

## Contract table

| producer_id | repo URL | native command | adapter method | expected cases (search order) | expected output | expected ingest path | minimum live cases | fixture fallback |
|-------------|----------|----------------|----------------|------------------------------|-----------------|----------------------|--------------------|------------------|
| `labtrust-gym` | https://github.com/fraware/LabTrust-Gym | `labtrust benchmark-reproducibility ...` | `LabTrustAdapter.benchmark_reproducibility` | `benchmarks/labtrust-qc-release`, `examples/pcs_qc_release/benchmark`, ... | `benchmark_runs/labtrust_reproducibility` | `benchmark_runs/labtrust_reproducibility/pcs_bench_ingest.v0.json` | 1 | `tests/fixtures/producer_ingest/labtrust_reproducibility/` (fallback: `labtrust/`) |
| `certifyedge` | https://github.com/fraware/CertifyEdge | `certifyedge benchmark certificates --profile tool_use_safety ...` | `CertifyEdgeAdapter.benchmark_certificates` | `benchmarks/certificates/tool_use_safety`, `benchmarks/tool_use_safety`, `services/pcs-certificate/benchmarks/certificates/tool_use_safety` | `benchmark_runs/tool_use_safety` | `benchmark_runs/tool_use_safety/pcs_bench_ingest.v0.json` | 1 | `tests/fixtures/producer_ingest/certifyedge/` |
| `provability-fabric` | https://github.com/SentinelOps-CI/provability-fabric | `pf benchmark admission ...` | `ProvabilityFabricAdapter.benchmark_admission` | `benchmarks/admission/labtrust_qc_release`, `benchmarks/labtrust_admission`, `adapters/pcs/benchmarks/admission/labtrust_qc_release` | `benchmark_runs/labtrust_admission` | `benchmark_runs/labtrust_admission/pcs_bench_ingest.v0.json` | 1 | `tests/fixtures/producer_ingest/provability_fabric/` |
| `scientific-memory` | https://github.com/fraware/scientific-memory | `just pcs-benchmark-rendering CASES=... OUT=...` | `ScientificMemoryAdapter.benchmark_rendering` | `benchmarks/rendering/labtrust_qc_release`, `benchmarks/labtrust_rendering`, `pipeline/benchmarks/rendering/labtrust_qc_release` | `benchmark_runs/labtrust_rendering` | `benchmark_runs/labtrust_rendering/pcs_bench_ingest.v0.json` | 1 | `tests/fixtures/producer_ingest/scientific_memory/` |

## Per-producer requirements

### labtrust-gym

- **Required embedded arrays:** `benchmark_runs`, `commands`, `logs`
- **Required artifact_refs:** one ref per `benchmark_runs[].signature_or_digest`
- **Release-grade:** non-empty runs, real `source_commit`, live commands, no simulate-only runs
- **Registry:** N/A (reproducibility benchmark)

### certifyedge

- **Required embedded arrays:** `coverage_reports`, `profile_coverage_reports`, `commands`, `logs` (`benchmark_runs` optional when coverage+profile populated)
- **Required artifact_refs:** refs for coverage and profile coverage digests
- **Release-grade:** non-empty coverage and profile coverage; commands; real commit

### provability-fabric

- **Required embedded arrays:** `benchmark_runs`, `failure_localization_reports`, `explain_quality_reports`, `commands`, `logs`
- **Registry:** `profiles/registry.json` or `registry.json`
- **Release-grade:** non-empty failure localization and explain-quality reports

### scientific-memory

- **Required embedded arrays:** `benchmark_runs`, `explain_quality_reports`, `commands`, `logs`
- **Release-grade:** non-empty explain-quality reports; rendering/query cases exercised

## Merge provenance

`aggregate_gate_report` writes `producer_merge_manifest.v0.json` beside the aggregate report and copies it into the packet:

```json
{
  "schema_version": "v0",
  "aggregate_report_path": "/path/to/reports/live-ci.json",
  "producer_reports": [
    {
      "producer_id": "certifyedge",
      "suite_id": "certifyedge-certificate-v0",
      "workflow_id": "tool_use_safety",
      "source_repo": "https://github.com/fraware/CertifyEdge",
      "source_commit": "<40-char hex>",
      "ingest_digest": "sha256:<64 hex>",
      "ingest_path": ".../pcs_bench_ingest.v0.json",
      "normalized_report_path": ".../certifyedge.normalized.json",
      "live_cases": 2,
      "coverage_count": 1,
      "explain_count": 0,
      "failure_localization_count": 0,
      "profile_coverage_count": 1
    }
  ]
}
```

## Diagnostics

```bash
pcs-bench producer-doctor \
  --pcs-core ../pcs-core \
  --labtrust ../LabTrust-Gym \
  --certifyedge ../CertifyEdge \
  --provability-fabric ../provability-fabric \
  --scientific-memory ../scientific-memory \
  --json-out reports/producer-doctor.json

# Non-zero exit only when explicitly requested:
pcs-bench producer-doctor --strict --json-out reports/producer-doctor.json
```

Checks per producer: repo exists, CLI smoke, benchmark cases dir, output dir writable, ingest present or generatable, schema + release-grade validation (with `--release-grade`), artifact_refs vs embedded digests.

## Gate commands

```bash
# Offline CI (fixture fallback allowed)
make producer-gate

# Release-grade live producers (no fixture fallback) → reports/live-ci.json
make live-ci

# Full integration
pcs-bench gate --live --run-producer-benchmarks --reproduce-smoke \
  --out reports/live-ci.json --out-packet packets/live-ci \
  --pcs-core ../pcs-core --labtrust ../LabTrust-Gym ...
```

Packet verification with reproduction smoke emits `packet_reproduction_report.v0.json` (valid/invalid case replay, explain-quality schema, Scientific Memory rendering sections, bundled `producer_ingests/` validation).
