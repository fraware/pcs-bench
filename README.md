# pcs-bench

Evaluation harness for [Proof-Carrying Science (PCS)](https://github.com/SentinelOps-CI/pcs-core). pcs-bench measures whether PCS releases are reproducible, explainable, auditable, formally covered, registry-compliant, and understandable across workflow domains.

pcs-bench orchestrates the PCS ecosystem from the outside. It does not own schemas, certificates, admission logic, or rendering.

## Ecosystem

| Repository | Role |
|------------|------|
| [pcs-core](https://github.com/SentinelOps-CI/pcs-core) | Protocol authority (schemas, registry, conformance) |
| [LabTrust-Gym](https://github.com/fraware/LabTrust-Gym) | Reference runtime workflow producer |
| [CertifyEdge](https://github.com/fraware/CertifyEdge) | Certificate and witness producer |
| [provability-fabric](https://github.com/SentinelOps-CI/provability-fabric) | Admission controller |
| [scientific-memory](https://github.com/fraware/scientific-memory) | Human-facing evidence and rendering |
| **pcs-bench** | Evaluation harness (this repo) |

## Install

```bash
pip install -e ".[dev]"
```

Use `pcs-bench` or `python -m pcs_bench` (recommended on Windows if the script is not on PATH). Configure sibling repo paths in `pcs-bench.yaml` or pass them on the CLI.

## Quick start

```bash
python scripts/materialize_fixtures.py

# Offline release prep (lint, tests, gate, producer-gate)
make release-prep

# Single-suite smoke
pcs-bench run --suite labtrust-qc-release --out reports/latest.json

# Live evaluation (sibling repos required)
make live-ci
make release-verify
```

On Windows: `.\make.ps1 gate`, `.\make.ps1 live-ci`.

## Common commands

| Task | Command |
|------|---------|
| List suites | `pcs-bench list-suites` |
| Validate cases | `pcs-bench validate-cases --suite all --dry-run` |
| Validate report | `pcs-bench validate-report --input reports/ci.json` |
| Export reviewer packet | `pcs-bench packet --report reports/ci.json --out packets/latest` |
| Verify packet + smoke | `pcs-bench verify-packet --packet packets/latest --reproduce-smoke` |
| Producer readiness | `pcs-bench producer-doctor --json-out reports/producer-doctor.json` |
| Release readiness | `pcs-bench release-readiness --strict` (after `make live-ci`) |
| Human report | `pcs-bench report --input reports/ci.json --format markdown --out reports/ci.md` |

## Documentation

Full guides and reference material: **[docs/README.md](docs/README.md)**

- [Release guide](docs/release.md) — checklist and artifacts before tagging
- [Running benchmarks](docs/execution.md) — modes, gates, CI, packets
- [Producer integration](docs/producers.md) — ingest contract and producer CLIs
- [Metrics](docs/metrics.md) · [Benchmark vocabulary](docs/benchmark-vocabulary.md) · [Architecture](docs/architecture.md)

## What this repo owns

- Benchmark orchestration and cross-repo adapters
- Suite selection, case execution, metric computation
- Report aggregation, baseline comparison, CI thresholds
- Reviewer packet export and verification

## What this repo does not own

PCS schemas, release manifests, certificates, runtime workflows, admission logic, scientific-memory rendering, or Lean theorem definitions. Those live in the respective ecosystem repositories; pcs-bench consumes them via public command-line interfaces only.

## License

Apache-2.0
