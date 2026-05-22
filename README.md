# pcs-bench

Evaluation harness for [Proof-Carrying Science (PCS)](https://github.com/SentinelOps-CI/pcs-core). pcs-bench measures whether PCS releases are reproducible, explainable, auditable, formally covered, registry-compliant, and understandable to humans across multiple workflow domains.

pcs-bench is **not** a protocol repo, workflow repo, certificate engine, verifier, or rendering layer. It orchestrates the PCS ecosystem from the outside and aggregates evaluation results.

## Ecosystem

| Repository | Role |
|------------|------|
| [pcs-core](https://github.com/SentinelOps-CI/pcs-core) | Protocol authority (schemas, registry, conformance) |
| [LabTrust-Gym](https://github.com/fraware/LabTrust-Gym) | Reference runtime workflow producer |
| [CertifyEdge](https://github.com/fraware/CertifyEdge) | Certificate and witness producer |
| [provability-fabric](https://github.com/SentinelOps-CI/provability-fabric) | PCS admission controller |
| [scientific-memory](https://github.com/fraware/scientific-memory) | Human-facing evidence and rendering |
| **pcs-bench** | Evaluation harness (this repo) |

## Install

```bash
pip install -e ".[dev]"
```

After install you can use either `pcs-bench` or `python -m pcs_bench` (recommended on Windows if the script is not on PATH).

Configure sibling repo paths in `pcs-bench.yaml` or pass them on the CLI.

## Quick start

```bash
pip install -e ".[dev]"
python scripts/materialize_fixtures.py

# Simulate (default): fixture sidecars + artifact analysis, no CLIs required
pcs-bench run --suite labtrust-qc-release --out reports/latest.json

# Full stack offline CI gate
pcs-bench run --suite all --simulate --ci --out reports/ci.json

# Live evaluation against sibling repo CLIs
pcs-bench check-adapters
pcs-bench run --suite labtrust-qc-release --live --out reports/live.json

# Validate benchmark cases
pcs-bench validate-cases --suite all --dry-run

# Reports and comparison
pcs-bench report --input reports/latest.json --format markdown --out reports/latest.md
pcs-bench compare --old reports/baseline.json --new reports/latest.json
pcs-bench explain --report reports/latest.json --case labtrust-trace-hash-tamper-v0
pcs-bench list-suites

# Strict BenchmarkReport.v0 validation (pcs-core schema)
pcs-bench validate-report --input reports/ci.json --pcs-core ../pcs-core

# Validate producer PcsBenchIngest.v0
pcs-bench validate-ingest --input ../CertifyEdge/benchmark_runs/tool_use_safety/pcs_bench_ingest.v0.json --pcs-core ../pcs-core

# Normalize producer-native benchmark output
pcs-bench ingest-producer-output --producer certifyedge --input ../CertifyEdge/benchmark_runs/tool_use_safety/pcs_bench_ingest.v0.json --out reports/certifyedge.normalized.json

# Producer diagnostics and contracts (see docs/producer-contracts.md)
pcs-bench producer-doctor --pcs-core ../pcs-core --json-out reports/producer-doctor.json
make producer-gate                    # offline: fixture ingest fallback
make producer-gate-release            # alias for live-ci
make live-ci                          # live release gate → reports/live-ci.json, packets/live-ci
make release-check                    # verify producers + live-ci artifacts (after live-ci)
pcs-bench release-readiness --strict  # one-shot readiness (see docs/PCS_RELEASE_CHECKLIST.md)

# Gate with producer benchmarks (live)
pcs-bench gate --suite all --live --run-producer-benchmarks --pcs-core ../pcs-core --labtrust ../LabTrust-Gym --certifyedge ../CertifyEdge --provability-fabric ../provability-fabric --scientific-memory ../scientific-memory

# Verify packet with reproduction smoke checks
pcs-bench verify-packet --packet packets/latest --reproduce-smoke

# Validate all offline producer ingest fixtures (CI-safe)
pcs-bench validate-producer-fixtures --pcs-core ../pcs-core

# Release-grade evidence (live adapters required for live_required suites)
pcs-bench run --suite all --live --ci --out reports/release.json

# Export reviewer packet and verify structure
pcs-bench packet --report reports/ci.json --out packets/latest
pcs-bench verify-packet --packet packets/latest

# Fixture integrity for reproducible benchmarks
pcs-bench verify-fixtures --write
pcs-bench verify-fixtures

# Scaffold config, filter cases, parallel simulate runs
pcs-bench init
pcs-bench run --suite labtrust-qc-release --cases labtrust-valid-release-v0,labtrust-trace-hash-tamper-v0
pcs-bench run --suite all --simulate --parallel 4

# Structured compare output
pcs-bench compare --old reports/baseline.json --new reports/latest.json --format json

# Full local release gate (fixtures + manifest + CI + report schema + packet)
pcs-bench gate

# Sync JSON schemas from a local pcs-core checkout
pcs-bench sync-schemas --pcs-core ../pcs-core

# Optional: copy real release bundles from LabTrust into case fixtures
python scripts/pull_release_fixtures.py --suite labtrust_qc_release
```

Or use `make gate` / `make ci` / `make packet`. On Windows: `.\make.ps1 gate`.

See [CI mode](docs/ci-mode.md), [Metrics](docs/metrics.md), and [Live release gate](docs/live-gate.md).

## What pcs-bench owns

- Benchmark orchestration and cross-repo adapters
- Suite selection, case execution, metric computation
- Report aggregation, baseline comparison, CI thresholds
- Human-readable evaluation reports

## What pcs-bench does not own

PCS schemas, release manifests, certificates, runtime workflows, PF admission logic, Scientific Memory rendering, or Lean theorem definitions. Those live in the respective ecosystem repos; pcs-bench consumes them via public CLIs only.

## Documentation

- [Architecture](docs/architecture.md)
- [Benchmark methodology](docs/benchmark-methodology.md)
- [Metrics](docs/metrics.md)
- [Benchmark vocabulary](docs/benchmark-vocabulary.md)
- [Adding a benchmark suite](docs/adding-a-benchmark-suite.md)
- [Interpreting results](docs/interpreting-results.md)
- [CI mode](docs/ci-mode.md)
- [Live release gate](docs/live-gate.md)

## License

Apache-2.0
