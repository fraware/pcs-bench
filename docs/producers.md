# Producer integration

Each PCS producer repository emits one canonical file: **`pcs_bench_ingest.v0.json`**, validated against schemas in [pcs-core](https://github.com/SentinelOps-CI/pcs-core). pcs-bench ingests these files and merges them with its own benchmark suites into a single `BenchmarkReport.v0`.

## Canonical ingest file

| Requirement | Rule |
|-------------|------|
| Filename | `pcs_bench_ingest.v0.json` |
| Schema | `PcsBenchIngest.v0` (pcs-core) |
| Embedded data | `benchmark_runs`, `coverage_reports`, `failure_localization_reports`, `explain_quality_reports`, `profile_coverage_reports`, `commands`, `logs`, `source_repo`, `source_commit`, digest |
| `artifact_refs` | Optional provenance records; they do not replace embedded objects |
| Native target | `make pcs-bench-producer` in each producer repo |

Sync schemas into pcs-bench:

```bash
pcs-bench sync-schemas --pcs-core ../pcs-core
```

## Producer paths

| Producer | Ingest path |
|----------|-------------|
| LabTrust-Gym | `benchmark_runs/labtrust_reproducibility/pcs_bench_ingest.v0.json` |
| CertifyEdge | `benchmark_runs/tool_use_safety/pcs_bench_ingest.v0.json` |
| provability-fabric | `benchmark_runs/labtrust_admission/pcs_bench_ingest.v0.json` |
| scientific-memory | `benchmark_runs/labtrust_rendering/pcs_bench_ingest.v0.json` |

## Per-producer requirements

### LabTrust-Gym

- **Required in ingest:** `benchmark_runs`, `commands`, `logs`
- **Release:** non-empty runs, real `source_commit`, live commands, no simulate-only runs
- **Artifact references:** one ref per `benchmark_runs[].signature_or_digest`

### CertifyEdge

- **Required in ingest:** `coverage_reports`, `profile_coverage_reports`, `commands`, `logs` (`benchmark_runs` optional when coverage and profile coverage are populated)
- **Release:** non-empty coverage and profile coverage; real commit

### provability-fabric

- **Required in ingest:** `benchmark_runs`, `failure_localization_reports`, `explain_quality_reports`, `commands`, `logs`
- **Registry:** `profiles/registry.json` or `registry.json`
- **Release:** non-empty failure localization and explain-quality reports

### scientific-memory

- **Required in ingest:** `benchmark_runs`, `explain_quality_reports`, `commands`, `logs`
- **Release:** non-empty explain-quality reports; rendering cases exercised

## Release-grade validation

`pcs-bench validate-ingest --release-grade` and live gates (without `--use-producer-fixtures`) require:

| Check | Applies to |
|-------|------------|
| `source_commit` is 40-character hex, not all zeros | all |
| `benchmark_runs` non-empty | all (CertifyEdge may satisfy via coverage + profile coverage only) |
| `commands` non-empty | all |
| `coverage_reports` non-empty | CertifyEdge |
| `failure_localization_reports` non-empty | provability-fabric |
| `explain_quality_reports` non-empty | provability-fabric, scientific-memory |
| `profile_coverage_reports` non-empty | CertifyEdge |
| No `execution_kind=simulate` on runs | all with runs |
| `artifact_refs` sidecars exist and digests match | when refs present |
| pcs-core schema validation | all |

Developer mode (`--use-producer-fixtures`) uses reference ingest files under `tests/fixtures/producer_ingest/` and marks aggregate evidence as **developer**. The gate also writes `producer_gate_result.v0.json` with `use_fixture_fallback: true`. Release gates reject `--live` combined with `--use-producer-fixtures`.

## CLI commands

```bash
# Readiness diagnostic (non-blocking by default)
pcs-bench producer-doctor \
  --pcs-core ../pcs-core \
  --labtrust ../LabTrust-Gym \
  --certifyedge ../CertifyEdge \
  --provability-fabric ../provability-fabric \
  --scientific-memory ../scientific-memory \
  --json-out reports/producer-doctor.json

pcs-bench producer-doctor --strict --release-grade

# Validate one ingest
pcs-bench validate-ingest --input path/to/pcs_bench_ingest.v0.json --pcs-core ../pcs-core
pcs-bench validate-ingest --input path/to/pcs_bench_ingest.v0.json --release-grade

# Check all producer repos
pcs-bench check-producer-ingests \
  --pcs-core ../pcs-core \
  --labtrust ../LabTrust-Gym \
  --certifyedge ../CertifyEdge \
  --provability-fabric ../provability-fabric \
  --scientific-memory ../scientific-memory

# Reference ingest only (CI-safe)
pcs-bench check-producer-ingests --fixtures-only --pcs-core ../pcs-core
pcs-bench validate-producer-fixtures --pcs-core ../pcs-core

# Normalize to BenchmarkReport.v0
pcs-bench ingest-producer-output \
  --producer certifyedge \
  --input ../CertifyEdge/benchmark_runs/tool_use_safety/pcs_bench_ingest.v0.json \
  --out reports/certifyedge.normalized.json

pcs-bench ingest-all-producers --out-dir reports/producers
```

## Gate behavior with producers

With `--run-producer-benchmarks` on `gate`:

1. Optionally runs each producer benchmark when the sibling repo is present.
2. Loads `pcs_bench_ingest.v0.json` from the paths above.
3. Validates each ingest and normalizes to internal report format.
4. Merges with pcs-bench suite results and recomputes metrics.
5. Writes `producer_merge_manifest.v0.json` beside the aggregate report.

Release-grade gates reuse a valid canonical ingest when already on disk. Re-run producer CLIs only when ingest is missing or invalid, or pass `--refresh-producer-ingests` on `gate`.

Reference ingest files live in `tests/fixtures/producer_ingest/` and are validated on every `gate` run.

## Merge manifest

`aggregate_gate_report` writes `producer_merge_manifest.v0.json` with producer provenance:

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
      "live_cases": 2
    }
  ]
}
```

## Implementation reference

Repo URLs, case search paths, and adapter command names are defined in `src/pcs_bench/producer_contracts.py` for maintainers. User-facing paths and commands above are the stable contract.
