# Release guide

This guide supports tagging a PCS ecosystem release. pcs-bench acts as the external evaluation gate, and each producer repository must emit a valid `pcs_bench_ingest.v0.json` as described in [Producer integration](producers.md).

## Prerequisites

Clone sibling repositories next to pcs-bench, with paths configurable in [pcs-bench.yaml](configuration.md).

| Repository | Role |
|------------|------|
| [pcs-core](https://github.com/SentinelOps-CI/pcs-core) | JSON schemas and protocol definitions |
| [LabTrust-Gym](https://github.com/fraware/LabTrust-Gym) | Reference workflow producer |
| [CertifyEdge](https://github.com/fraware/CertifyEdge) | Certificate and witness producer |
| [provability-fabric](https://github.com/SentinelOps-CI/provability-fabric) | Admission controller |
| [scientific-memory](https://github.com/fraware/scientific-memory) | Evidence rendering |

Each producer implements `make pcs-bench-producer` and writes ingest to the path listed in [producers.md](producers.md).

## Release workflow

### 1. Refresh producer outputs

```bash
cd ../LabTrust-Gym && make pcs-bench-producer
cd ../CertifyEdge && make pcs-bench-producer
cd ../provability-fabric && make pcs-bench-producer
cd ../scientific-memory && make pcs-bench-producer
```

### 2. Validate pcs-bench

**Offline prep** runs on every pull request and only needs this repository.

```bash
cd pcs-bench
pip install -e ".[dev]"
make release-prep
```

That target runs lint, schema sync, release-grade fixture validation, pytest, `gate`, and `producer-gate`.

**Live release** needs sibling repositories on disk.

```bash
make check-producer-ingests
make live-ci
make release-verify
```

On Windows, use `.\make.ps1 release-prep`, `.\make.ps1 live-ci`, and `.\make.ps1 release-verify`.

### 3. Readiness check

After `make live-ci`, `make release-verify` runs `release-readiness --strict`. You can also run it manually.

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

A successful run prints `PCS release readiness: OK`.

## Expected artifacts

After `make live-ci`, expect the following outputs.

| File or directory | Purpose |
|-------------------|---------|
| `reports/live-ci.json` | Combined `BenchmarkReport.v0` with `evidence_grade: release` |
| `reports/producer_merge_manifest.v0.json` | Producer provenance and ingest digests |
| `reports/producer_gate_result.v0.json` | Gate pass or fail summary |
| `reports/producer-doctor.json` | Optional producer readiness diagnostic |
| `reports/release-readiness.json` | Output from `release-verify` |
| `packets/live-ci/` | Reviewer packet |
| `packets/live-ci/packet_reproduction_report.v0.json` | Packet smoke-check results |

Offline gates (`make gate`, `make producer-gate`) set `evidence_grade: developer` on the aggregate report. When reference ingest data is used, `reports/producer_gate_result.v0.json` contains `use_fixture_fallback: true`.

## Release evidence rules

Live release gates that omit `--use-producer-fixtures` require the following.

- Real 40-character `source_commit` values that use non-zero hex digits
- Non-empty `commands` in each producer ingest
- Producer-specific embedded reports populated (runs, coverage, explain quality, failure localization, profile coverage as applicable)
- `artifact_refs` digests that match embedded objects when references are present
- Benchmark runs that use live `execution_kind` values
- Validation against pcs-core schemas

Per-producer details appear in [producers.md](producers.md).

## Continuous integration

GitHub Actions workflows live in `.github/workflows/`.

| Workflow | Jobs | Purpose |
|----------|------|---------|
| **PCS Benchmark** (`benchmark.yml`) | `lint-and-test`, `simulate-gate`, `producer-offline-gate` | Every push and PR (ruff, pytest, offline gates) |
| **PCS Producer Gate** (`producer-gate.yml`) | ingest validation, offline gate, optional live gate | Manual dispatch for full producer checkout |

Pull requests run entirely inside this repository. An optional live gate runs when you enable it in the workflow dispatch UI.

## Diagnostic commands

```bash
pcs-bench producer-doctor --json-out reports/producer-doctor.json \
  --pcs-core ../pcs-core --labtrust ../LabTrust-Gym \
  --certifyedge ../CertifyEdge --provability-fabric ../provability-fabric \
  --scientific-memory ../scientific-memory

pcs-bench producer-doctor --strict --release-grade

pcs-bench validate-ingest --input path/to/pcs_bench_ingest.v0.json --release-grade
```

`producer-doctor` exits zero by default and exits with code 2 under `--strict` when any producer is unready.
