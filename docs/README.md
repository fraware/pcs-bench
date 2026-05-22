# Documentation

pcs-bench evaluates Proof-Carrying Science releases by running benchmark cases and aggregating results from producer repositories. Schemas and protocol rules are defined in [pcs-core](https://github.com/SentinelOps-CI/pcs-core), and this repository implements the harness that runs those evaluations.

## Guides

| Document | Audience | Contents |
|----------|----------|----------|
| [Release guide](release.md) | Release managers | Producer refresh, `release-prep`, `live-ci`, artifacts, CI |
| [Running benchmarks](execution.md) | Daily users | Simulate vs live, gates, packets, smoke checks |
| [Producer integration](producers.md) | Producer repo maintainers | `pcs_bench_ingest.v0.json`, validation, merge manifest |
| [Configuration](configuration.md) | All users | `pcs-bench.yaml`, repo paths, thresholds, timeouts |

## Reference

| Document | Contents |
|----------|----------|
| [Architecture](architecture.md) | Modules, pipelines, workspaces |
| [Benchmark methodology](benchmark-methodology.md) | Principles and suite layout |
| [Metrics](metrics.md) | Eight scores and applicability states |
| [Benchmark vocabulary](benchmark-vocabulary.md) | Harness status vs system outcome |
| [Interpreting results](interpreting-results.md) | Reports, packets, comparisons |
| [Adding a benchmark suite](adding-a-benchmark-suite.md) | New suite checklist |

## Command-line interface

| Command | Purpose |
|---------|---------|
| `run` | Execute one or more suites |
| `gate` | Full pipeline (fixtures, cases, benchmark, report, packet) |
| `producer-doctor` | Producer repository readiness (exits zero by default) |
| `check-producer-ingests` | Validate ingest files in producer repos |
| `validate-ingest` | Validate a single `pcs_bench_ingest.v0.json` |
| `validate-producer-fixtures` | Validate embedded reference ingests |
| `release-readiness` | One-shot status after `live-ci` |
| `packet` / `verify-packet` | Reviewer bundle export and verification |
| `validate-report` / `validate-cases` | Schema and case checks |
| `sync-schemas` | Copy JSON schemas from a local pcs-core checkout |

## Make targets

| Target | When to use |
|--------|-------------|
| `release-prep` | Every PR (lint, test, offline gates) |
| `gate` | Standard offline CI gate |
| `producer-gate` | Offline gate including four producer ingests |
| `live-ci` | Release gate with live CLIs |
| `release-verify` | Strict readiness after `live-ci` |

```bash
pip install -e ".[dev]"
make release-prep
```

On Windows, run `.\make.ps1 release-prep` and see `make.ps1` for all targets.

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md).
