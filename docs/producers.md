# Producer integration

Each PCS producer repository emits one canonical file named **`pcs_bench_ingest.v0.json`**, validated against schemas in [pcs-core](https://github.com/SentinelOps-CI/pcs-core). pcs-bench ingests these files and merges them with its own benchmark suites into a single `BenchmarkReport.v0`.

## Canonical ingest file

| Requirement | Rule |
|-------------|------|
| Filename | `pcs_bench_ingest.v0.json` |
| Schema | `PcsBenchIngest.v0` (pcs-core) |
| Embedded data | `benchmark_runs`, `coverage_reports`, `failure_localization_reports`, `explain_quality_reports`, `profile_coverage_reports`, `commands`, `logs`, `source_repo`, `source_commit`, digest |
| `artifact_refs` | Optional provenance records that supplement embedded objects |
| Native target | `make pcs-bench-producer` in each producer repo |

Sync schemas into pcs-bench with the following command.

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

The ingest must include `benchmark_runs`, `commands`, and `logs`. Release-grade ingests need non-empty runs, a real `source_commit`, live commands, and runs that use live execution kinds. Provide one artifact reference per `benchmark_runs[].signature_or_digest`.

### CertifyEdge

The ingest must include `coverage_reports`, `profile_coverage_reports`, `commands`, and `logs`. `benchmark_runs` may be empty when coverage and profile coverage are fully populated. Release-grade ingests need non-empty coverage and profile coverage plus a real commit.

### provability-fabric

The ingest must include `benchmark_runs`, `failure_localization_reports`, `explain_quality_reports`, `commands`, and `logs`. Registry files live at `profiles/registry.json` or `registry.json`. Release-grade ingests need non-empty failure localization and explain-quality reports.

### scientific-memory

The ingest must include `benchmark_runs`, `explain_quality_reports`, `commands`, and `logs`. Release-grade ingests need non-empty explain-quality reports and exercised rendering cases.

## Release-grade validation

`pcs-bench validate-ingest --release-grade` and live gates that omit `--use-producer-fixtures` apply the checks below.

| Check | Applies to |
|-------|------------|
| `source_commit` is 40-character hex with non-zero digits | all |
| `benchmark_runs` non-empty | all (CertifyEdge may satisfy via coverage + profile coverage only) |
| `commands` non-empty | all |
| `coverage_reports` non-empty | CertifyEdge |
| `failure_localization_reports` non-empty | provability-fabric |
| `explain_quality_reports` non-empty | provability-fabric, scientific-memory |
| `profile_coverage_reports` non-empty | CertifyEdge |
| Runs use live `execution_kind` | all with runs |
| `artifact_refs` sidecars exist and digests match | when refs present |
| pcs-core schema validation | all |

**Reference ingest mode** (`--use-producer-fixtures`) reads files under `tests/fixtures/producer_ingest/` and sets aggregate `evidence_grade` to `developer`. The gate writes `producer_gate_result.v0.json` with `use_fixture_fallback: true`. Release gates refuse `--live` when combined with `--use-producer-fixtures`.

## CLI commands

```bash
pcs-bench producer-doctor \
  --pcs-core ../pcs-core \
  --labtrust ../LabTrust-Gym \
  --certifyedge ../CertifyEdge \
  --provability-fabric ../provability-fabric \
  --scientific-memory ../scientific-memory \
  --json-out reports/producer-doctor.json

pcs-bench producer-doctor --strict --release-grade

pcs-bench validate-ingest --input path/to/pcs_bench_ingest.v0.json --pcs-core ../pcs-core
pcs-bench validate-ingest --input path/to/pcs_bench_ingest.v0.json --release-grade

pcs-bench check-producer-ingests \
  --pcs-core ../pcs-core \
  --labtrust ../LabTrust-Gym \
  --certifyedge ../CertifyEdge \
  --provability-fabric ../provability-fabric \
  --scientific-memory ../scientific-memory

pcs-bench check-producer-ingests --fixtures-only --pcs-core ../pcs-core
pcs-bench validate-producer-fixtures --pcs-core ../pcs-core

pcs-bench ingest-producer-output \
  --producer certifyedge \
  --input ../CertifyEdge/benchmark_runs/tool_use_safety/pcs_bench_ingest.v0.json \
  --out reports/certifyedge.normalized.json

pcs-bench ingest-all-producers --out-dir reports/producers
```

`producer-doctor` exits zero by default and uses exit code 2 under `--strict` when a producer is unready.

## Gate behavior with producers

With `--run-producer-benchmarks` on `gate`, the harness follows this sequence.

1. Optionally runs each producer benchmark when the sibling repo is present.
2. Loads `pcs_bench_ingest.v0.json` from the paths above.
3. Validates each ingest and normalizes to internal report format.
4. Merges with pcs-bench suite results and recomputes metrics.
5. Writes `producer_merge_manifest.v0.json` beside the aggregate report.
6. Writes `producer_gate_result.v0.json` with pass or fail status and harness metadata.

Release-grade gates reuse a valid canonical ingest when it already exists on disk. Re-run producer CLIs when ingest is missing or invalid, or pass `--refresh-producer-ingests` on `gate`.

Reference ingest files under `tests/fixtures/producer_ingest/` are validated on every `gate` run.

## Merge manifest

When producer results are merged, pcs-bench writes `producer_merge_manifest.v0.json`.

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

Reviewer packets copy this manifest and per-producer ingest files under `producer_ingests/` when those files exist.

## Maintainer reference

Repo URLs, case search paths, and adapter command names are defined in `src/pcs_bench/producer_contracts.py`. User-facing paths and commands in this document form the stable public contract.
