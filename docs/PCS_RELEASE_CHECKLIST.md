# PCS release checklist

Use this checklist before tagging a PCS ecosystem release. pcs-bench is the external gate; each producer must emit `pcs_bench_ingest.v0.json` per [producer-contracts.md](producer-contracts.md).

## 1. Producer repos (sibling checkouts)

Each repo must expose `make pcs-bench-producer` and write ingest to the canonical path:

| Producer | Command | Ingest path |
|----------|---------|-------------|
| LabTrust-Gym | `make pcs-bench-producer` | `benchmark_runs/labtrust_reproducibility/pcs_bench_ingest.v0.json` |
| CertifyEdge | `make pcs-bench-producer` | `benchmark_runs/tool_use_safety/pcs_bench_ingest.v0.json` |
| provability-fabric | `make pcs-bench-producer` | `benchmark_runs/labtrust_admission/pcs_bench_ingest.v0.json` |
| scientific-memory | `make pcs-bench-producer` | `benchmark_runs/labtrust_rendering/pcs_bench_ingest.v0.json` |

## 2. pcs-bench validation (local)

```bash
cd pcs-bench
pip install -e ".[dev]"
make schemas
make validate-producer-ingest-release
make check-producer-ingests --release-grade   # via pcs-bench CLI / Makefile deps
make producer-gate                            # offline: fixtures + simulate
make live-ci                                  # live: no fixture fallback
make release-check                            # doctor + ingests + live-ci artifacts
pytest -q
```

## 3. Expected release artifacts

After `make live-ci`:

| Artifact | Purpose |
|----------|---------|
| `reports/live-ci.json` | Aggregate `BenchmarkReport.v0` with `evidence_grade: release` |
| `reports/producer_merge_manifest.v0.json` | Producer provenance and ingest digests |
| `reports/producer_gate_result.v0.json` | Gate pass/fail summary |
| `reports/producer-doctor.json` | Optional diagnostic JSON |
| `packets/live-ci/` | Reviewer packet |
| `packets/live-ci/packet_reproduction_report.v0.json` | Reproduce-smoke results |

Offline gates set `evidence_grade: developer` and `fixture_fallback_used: true` when using `--use-producer-fixtures`.

## 4. One-shot readiness command

```bash
pcs-bench release-readiness --strict \
  --pcs-core ../pcs-core \
  --labtrust ../LabTrust-Gym \
  --certifyedge ../CertifyEdge \
  --provability-fabric ../provability-fabric \
  --scientific-memory ../scientific-memory \
  --live-ci-report reports/live-ci.json \
  --live-ci-packet packets/live-ci \
  --json-out reports/release-readiness.json
```

## 5. CI

- **PR / push**: `lint-and-test` + `producer-offline-gate` (fixtures, no sibling repos required).
- **Manual**: GitHub Actions `PCS Producer Gate` with `run_live: true` checks out all producer repos and runs the live gate.

## 6. Release-grade rules (summary)

- Real 40-char `source_commit` (not all zeros)
- Non-empty `commands`
- Producer-specific embedded arrays populated (runs, coverage, explain, failure localization, profile coverage)
- `artifact_refs` digests match embedded objects; sidecars on disk for canonical types
- No `execution_kind=simulate` on release runs
- pcs-core schema validation passes

Full matrix: [producer-contracts.md](producer-contracts.md).
