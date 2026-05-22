# Producer contract matrix

This document is the implementation reference for `producer_gate.py`, `producer_contracts.py`, and `pcs-bench producer-doctor`. Each PCS producer must emit `PcsBenchIngest.v0` at a canonical path; pcs-bench validates, normalizes, and merges those ingests into an aggregate `BenchmarkReport.v0`.

## Contract table

| producer_id | repo URL | native benchmark command | expected output directory | expected ingest path | required schemas | adapter method | minimum live cases | fixture fallback | release-grade status |
|-------------|----------|--------------------------|---------------------------|----------------------|------------------|----------------|--------------------|------------------|----------------------|
| `labtrust-gym` | https://github.com/fraware/LabTrust-Gym | `labtrust benchmark-reproducibility --pcs-core <pcs-core> --certifyedge-bin <certifyedge> --runs <n> --out <out>` | `benchmark_runs/labtrust_reproducibility` | `benchmark_runs/labtrust_reproducibility/pcs_bench_ingest.v0.json` | PcsBenchIngest.v0, BenchmarkRun.v0, BenchmarkArtifactRef.v0, benchmark_command_entry | `LabTrustAdapter.benchmark_reproducibility` | 1 | `tests/fixtures/producer_ingest/labtrust/` | contract-defined |
| `certifyedge` | https://github.com/fraware/CertifyEdge | `certifyedge benchmark certificates --profile tool_use_safety --cases <cases> --out <out>` | `benchmark_runs/tool_use_safety` | `benchmark_runs/tool_use_safety/pcs_bench_ingest.v0.json` | PcsBenchIngest.v0, CoverageReport.v0, ProfileCoverageReport.v0, BenchmarkArtifactRef.v0, benchmark_command_entry | `CertifyEdgeAdapter.benchmark_certificates` | 1 | `tests/fixtures/producer_ingest/certifyedge/` | contract-defined |
| `provability-fabric` | https://github.com/SentinelOps-CI/provability-fabric | `pf benchmark admission --cases <cases> --registry <registry> --out <out>` | `benchmark_runs/labtrust_admission` | `benchmark_runs/labtrust_admission/pcs_bench_ingest.v0.json` | PcsBenchIngest.v0, FailureLocalizationResult.v0, ExplainQualityReport.v0, ProfileCoverageReport.v0, BenchmarkArtifactRef.v0, benchmark_command_entry | `ProvabilityFabricAdapter.benchmark_admission` | 1 | `tests/fixtures/producer_ingest/provability_fabric/` | contract-defined |
| `scientific-memory` | https://github.com/fraware/scientific-memory | `just pcs-benchmark-rendering CASES=<cases> OUT=<out>` | `benchmark_runs/labtrust_rendering` | `benchmark_runs/labtrust_rendering/pcs_bench_ingest.v0.json` | PcsBenchIngest.v0, ExplainQualityReport.v0, BenchmarkArtifactRef.v0, benchmark_command_entry | `ScientificMemoryAdapter.benchmark_rendering` | 1 | `tests/fixtures/producer_ingest/scientific_memory/` | contract-defined |

## Benchmark case search paths

When a producer repo layout drifts, pcs-bench tries these directories in order (first match wins; selection is logged):

### LabTrust-Gym

- `benchmarks/labtrust-qc-release`
- `benchmarks/labtrust_reproducibility`

Reproducibility benchmark output is resolved explicitly to `benchmark_runs/labtrust_reproducibility/` (canonical ingest path above). Scratch `--out` may also emit `pcs_bench_ingest.v0.json`.

### CertifyEdge

1. `benchmarks/certificates/tool_use_safety`
2. `benchmarks/tool_use_safety`
3. `services/pcs-certificate/benchmarks/certificates/tool_use_safety`

### Provability Fabric

1. `benchmarks/admission/labtrust_qc_release`
2. `benchmarks/labtrust_admission`
3. `adapters/pcs/benchmarks/admission/labtrust_qc_release`

Registry: `profiles/registry.json`, then `registry.json`.

### Scientific Memory

1. `benchmarks/rendering/labtrust_qc_release`
2. `benchmarks/labtrust_rendering`
3. `pipeline/benchmarks/rendering/labtrust_qc_release`

## Release-grade adequacy

Schema validation is necessary but not sufficient for `pcs-bench gate --live --run-producer-benchmarks`. With `--release-grade` (default for live producer aggregation), ingests must also satisfy:

| Check | Applies to |
|-------|------------|
| `benchmark_runs` non-empty | all producers (CertifyEdge may use coverage+profile-only ingest when both arrays are populated) |
| `coverage_reports` non-empty when producer exports coverage | certifyedge |
| No run with `execution_kind=simulate` or `system_admission_outcome=not_evaluated` for all runs | all with runs |
| `source_commit` not all zeros | all |
| `artifact_refs` sidecar files resolvable under producer repo | when refs present |
| `failure_localization_reports` non-empty | provability-fabric |
| `explain_quality_reports` non-empty | provability-fabric, scientific-memory |
| `profile_coverage_reports` non-empty | certifyedge |

Developer mode (`validate-ingest` without `--release-grade`, or gate with `--use-producer-fixtures`) surfaces the same issues as warnings only where applicable.

## Merge provenance

`merge_benchmark_reports` writes `producer_merge_manifest.v0.json` beside the aggregate report:

```json
{
  "schema_version": "v0",
  "producer_reports": [
    {
      "producer_id": "certifyedge",
      "suite_id": "certifyedge-certificate-v0",
      "source_repo": "https://github.com/fraware/CertifyEdge",
      "source_commit": "<40-char hex>",
      "ingest_digest": "sha256:<64 hex>"
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
```

This command does not fail the gate; it reports repo, CLI, case path, output dir, ingest, and validation status per producer.
