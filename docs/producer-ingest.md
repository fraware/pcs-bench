# Producer ingest (PcsBenchIngest.v0)

pcs-bench consumes **one canonical contract** from each PCS producer repository. Producers emit `pcs_bench_ingest.v0.json`; the harness does not parse private benchmark formats outside optional `details` blobs.

## Contract

| Field | Role |
|-------|------|
| `producer_id` | `certifyedge`, `provability-fabric`, `labtrust-gym`, or `scientific-memory` |
| `suite_id` / `workflow_id` | Producer benchmark identity |
| `benchmark_runs` | `BenchmarkRun.v0` records (commands, artifacts, observed outcomes) |
| `coverage_reports` | `CoverageReport.v0` per metric domain |
| `explain_quality_reports` | `ExplainQualityReport.v0` |
| `profile_coverage_reports` | `ProfileCoverageReport.v0` |
| `failure_localization_reports` | `FailureLocalizationResult.v0` |
| `commands` | Top-level `benchmark_command_entry` audit trail |
| `logs` | Paths or log identifiers |
| `artifact_refs` | `BenchmarkArtifactRef.v0` (object refs, not bare path strings) |
| `source_commit` | 40-char lowercase git commit |
| `signature_or_digest` | `sha256:<64 hex>` |

Schema source of truth: **pcs-core** (`schemas/PcsBenchIngest.v0.schema.json`). Sync into pcs-bench with:

```bash
pcs-bench sync-schemas --pcs-core ../pcs-core
```

## Producer output locations

| Producer | Ingest path |
|----------|-------------|
| LabTrust-Gym | `benchmark_runs/labtrust_reproducibility/pcs_bench_ingest.v0.json` |
| CertifyEdge | `benchmark_runs/tool_use_safety/pcs_bench_ingest.v0.json` |
| provability-fabric | `benchmark_runs/labtrust_admission/pcs_bench_ingest.v0.json` |
| scientific-memory | `benchmark_runs/labtrust_rendering/pcs_bench_ingest.v0.json` |

## CLI

```bash
# Structural + semantic validation (schema + pcs-core artifact_ref rules)
pcs-bench validate-ingest --input path/to/pcs_bench_ingest.v0.json --pcs-core ../pcs-core

# Optional second opinion via pcs-core CLI
pcs-bench validate-ingest --input path/to/pcs_bench_ingest.v0.json --use-pcs-validate

# All offline fixtures (CI-safe; synced from pcs-core golden examples)
pcs-bench validate-producer-fixtures --pcs-core ../pcs-core
python scripts/sync_pcs_core_ingest_fixtures.py --pcs-core ../pcs-core

# Check each producer repo for ingest file presence + validity
make check-producer-ingests
# or:
pcs-bench check-producer-ingests \
  --pcs-core ../pcs-core \
  --labtrust ../LabTrust-Gym \
  --certifyedge ../CertifyEdge \
  --provability-fabric ../provability-fabric \
  --scientific-memory ../scientific-memory

# Batch normalize all producer ingests
pcs-bench ingest-all-producers --out-dir reports/producers

# Normalize to BenchmarkReport.v0
pcs-bench ingest-producer-output \
  --producer certifyedge \
  --input ../CertifyEdge/benchmark_runs/tool_use_safety/pcs_bench_ingest.v0.json \
  --out reports/certifyedge.normalized.json

# Offline producer gate (simulate suites + golden fixture ingests)
make producer-gate

# Live gate: real CLIs for pcs-bench suites; golden fixture ingests when repos lack pcs_bench_ingest.v0.json
make producer-gate-live

# Partial live (fixture fallback per case when a CLI is missing)
make producer-gate-hybrid

# Or explicitly:
pcs-bench gate --suite all --run-producer-benchmarks --use-producer-fixtures \
  --reproduce-smoke \
  --pcs-core ../pcs-core \
  --labtrust ../LabTrust-Gym \
  --certifyedge ../CertifyEdge \
  --provability-fabric ../provability-fabric \
  --scientific-memory ../scientific-memory
```

## Gate behavior

With `--run-producer-benchmarks`:

1. Optionally runs each producer benchmark CLI when the sibling repo is present.
2. Loads `pcs_bench_ingest.v0.json` from the paths above.
3. Validates each ingest, normalizes to internal `BenchmarkReport`, merges with the pcs-bench suite run.
4. Recomputes harness metrics on the combined run set while preserving producer `coverage` blocks.
5. Fails the gate if any of the four ingests are missing or invalid (strict mode).

With `--use-producer-fixtures`, missing repo ingests fall back to `tests/fixtures/producer_ingest/` (synced from pcs-core golden examples). Use this for local `make producer-gate` when sibling repos have not emitted `pcs_bench_ingest.v0.json` yet.

Every gate run also validates embedded fixtures under `tests/fixtures/producer_ingest/`.

## Packet reproduction

`pcs-bench verify-packet --reproduce-smoke` checks:

- One valid and one invalid case reproduce via fixture sidecars.
- An `ExplainQualityReport.v0` is present and schema-valid.
- A Scientific Memory rendering fixture includes all required sections.

Use `--reproduce-smoke` on `gate` to run the same checks on the exported packet.

## Offline fixtures

Regression fixtures live in `tests/fixtures/producer_ingest/{certifyedge,provability_fabric,scientific_memory,labtrust}/`. They are validated on every `pcs-bench gate` and in CI.
