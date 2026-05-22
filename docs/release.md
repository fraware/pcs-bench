# Release guide

Use this guide before tagging a PCS ecosystem release. pcs-bench is the external evaluation gate; each producer repository must emit a valid `pcs_bench_ingest.v0.json` (see [Producer integration](producers.md)).

## Prerequisites

Clone sibling repositories next to pcs-bench (paths are configurable in `pcs-bench.yaml`):

| Repository | Role |
|------------|------|
| [pcs-core](https://github.com/SentinelOps-CI/pcs-core) | JSON schemas and protocol definitions |
| [LabTrust-Gym](https://github.com/fraware/LabTrust-Gym) | Reference workflow producer |
| [CertifyEdge](https://github.com/fraware/CertifyEdge) | Certificate and witness producer |
| [provability-fabric](https://github.com/SentinelOps-CI/provability-fabric) | Admission controller |
| [scientific-memory](https://github.com/fraware/scientific-memory) | Evidence rendering |

Each producer must implement `make pcs-bench-producer` and write ingest to the path listed in [producers.md](producers.md).

## Release workflow

### 1. Refresh producer outputs

```bash
cd ../LabTrust-Gym && make pcs-bench-producer
cd ../CertifyEdge && make pcs-bench-producer
cd ../provability-fabric && make pcs-bench-producer
cd ../scientific-memory && make pcs-bench-producer
```

### 2. Validate pcs-bench

**Offline prep** (no sibling CLIs; run on every PR):

```bash
cd pcs-bench
pip install -e ".[dev]"
make release-prep
```

Runs: lint, schema sync, release-grade fixture validation, pytest, `gate`, `producer-gate`.

**Live release** (sibling repos on disk):

```bash
make check-producer-ingests
make live-ci
make release-verify
```

Windows: `.\make.ps1 release-prep`, `.\make.ps1 live-ci`, `.\make.ps1 release-verify`.

### 3. One-shot readiness check

After `make live-ci`:

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

## Expected artifacts

After `make live-ci`:

| File or directory | Purpose |
|-------------------|---------|
| `reports/live-ci.json` | Combined `BenchmarkReport.v0` with release evidence |
| `reports/producer_merge_manifest.v0.json` | Producer provenance and ingest digests |
| `reports/producer_gate_result.v0.json` | Gate pass or fail summary |
| `reports/producer-doctor.json` | Optional producer readiness diagnostic |
| `packets/live-ci/` | Reviewer packet (cases, report, manifests) |
| `packets/live-ci/packet_reproduction_report.v0.json` | Packet smoke-check results |

Offline gates (`make producer-gate`, `make gate`) label evidence as **developer** in the aggregate report. When reference ingest data is used, see `reports/producer_gate_result.v0.json` (`use_fixture_fallback: true`).

## Release evidence rules

Live release gates (without `--use-producer-fixtures`) require:

- Real 40-character `source_commit` (not all zeros)
- Non-empty `commands` in each producer ingest
- Producer-specific embedded reports populated (runs, coverage, explain quality, failure localization, profile coverage as applicable)
- `artifact_refs` digests match embedded objects when references are present
- No `execution_kind=simulate` on benchmark runs
- Validation against pcs-core schemas

Full per-producer matrix: [producers.md](producers.md).

## Continuous integration

| Trigger | What runs |
|---------|-----------|
| Pull request | Unit tests + offline producer gate (reference ingest data; no sibling repos required) |
| Manual workflow | Optional live producer gate with all repositories checked out |

GitHub Actions workflow: **PCS Producer Gate** (`producer-gate.yml`).

## Diagnostic commands

```bash
# Non-blocking producer readiness table + JSON
pcs-bench producer-doctor --json-out reports/producer-doctor.json \
  --pcs-core ../pcs-core --labtrust ../LabTrust-Gym \
  --certifyedge ../CertifyEdge --provability-fabric ../provability-fabric \
  --scientific-memory ../scientific-memory

# Strict exit if any producer is not ready
pcs-bench producer-doctor --strict --release-grade --json-out reports/producer-doctor.json

# Validate a single ingest file
pcs-bench validate-ingest --input path/to/pcs_bench_ingest.v0.json --release-grade
```
