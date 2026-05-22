# Running benchmarks

## Execution modes

| Mode | Flag | When to use |
|------|------|-------------|
| Simulate | `--simulate` (default) | Development and CI when producer CLIs are absent from the machine |
| Live | `--live` | Release evaluation against real command-line tools |
| Hybrid | `--hybrid` | Live first, then expected outcome files when a CLI returns exit 127 |
| Dry run | `--dry-run` | Plan a run while skipping external command execution |

Reports record `execution_mode` and `evidence_grade` in `summary`.

| `evidence_grade` | Typical run |
|------------------|-------------|
| `release` | `--ci` and `--live` together |
| `developer` | simulate, hybrid, or producer gate with reference ingest data |

Suites with `live_required_for_release: true` in `suite.yaml` fail CI when run in simulate mode with zero live cases.

Configuration is documented in [configuration.md](configuration.md).

## Make targets

| Target | What it runs |
|--------|----------------|
| `release-prep` | `lint`, `schemas`, `validate-producer-ingest-release`, `pytest`, `gate`, `producer-gate` |
| `gate` | Offline gate producing `reports/ci.json` and `packets/latest` |
| `producer-gate` | Offline gate with four producer ingests (reference data allowed) |
| `live-ci` | `producer-doctor`, `check-producer-ingests --release-grade`, live `gate` with producers |
| `release-verify` | `release-readiness --strict` over `live-ci` artifacts |
| `ci` | `gate` plus Markdown and HTML reports |

On Windows, run `.\make.ps1 <target>`.

## Standard offline gate

This path only requires the pcs-bench repository.

```bash
make gate
```

Equivalent invocation.

```bash
pcs-bench gate --out reports/ci.json --out-packet packets/latest --reproduce-smoke
```

Pipeline steps are as follows.

1. Materialize fixtures
2. Verify fixture manifest
3. Validate all benchmark cases
4. Validate reference producer ingests under `tests/fixtures/producer_ingest/`
5. Run all suites in simulate mode with `--ci` thresholds
6. Validate `BenchmarkReport.v0`
7. Export reviewer packet
8. Verify packet (optional reproduction smoke)

## Producer offline gate

This gate includes harness suites plus four producer `pcs_bench_ingest.v0.json` files, and reference ingest data is permitted.

```bash
make producer-gate
```

The command uses `--run-producer-benchmarks --use-producer-fixtures`. The gate refuses `--live` when combined with `--use-producer-fixtures`.

Harness-only metadata such as `use_fixture_fallback` is written to `reports/producer_gate_result.v0.json` and stays outside the aggregate `BenchmarkReport.v0` summary.

## Live release gate

This path needs sibling repositories on disk as described in [configuration.md](configuration.md).

```bash
make live-ci
make release-verify
```

`live-ci` runs the following gate.

```bash
pcs-bench gate --suite all --live --run-producer-benchmarks --reproduce-smoke \
  --out reports/live-ci.json --out-packet packets/live-ci \
  --pcs-core ../pcs-core \
  --labtrust ../LabTrust-Gym --certifyedge ../CertifyEdge \
  --provability-fabric ../provability-fabric --scientific-memory ../scientific-memory
```

## Progressive live rollout

| Step | Command |
|------|---------|
| 1 | `pcs-bench run --suite labtrust-qc-release --live --ci` |
| 2 | `pcs-bench run --suite tool-use-safety --live --ci` |
| 3 | `pcs-bench run --suite computation-reproducibility --live --ci` |
| 4 | `pcs-bench run --suite all --live --ci` |

Before live runs, confirm adapters respond.

```bash
pcs-bench check-adapters --pcs-core ../pcs-core --labtrust ../LabTrust-Gym
```

## CI failure conditions

With `--ci`, the process exits non-zero when any of the following occur.

- A valid release case is rejected
- An invalid release case is admitted
- A measured metric falls below its threshold in `pcs-bench.yaml`
- A required metric remained unmeasured
- The report fails `BenchmarkReport.v0` validation
- A live-required suite ran with zero live cases while execution stayed in simulate mode

Optional metrics with `insufficient_cases` fail CI only when the suite lists them under `required_metrics`.

## Packets and reproduction smoke

```bash
pcs-bench packet --report reports/ci.json --out packets/latest
pcs-bench verify-packet --packet packets/latest --reproduce-smoke
```

Reproduction smoke writes `packet_reproduction_report.v0.json` in the packet directory and checks the following.

- One valid and one invalid case reproduce expected outcomes
- Explain-quality JSON validates against schema
- Scientific-memory rendering includes required sections
- Bundled producer ingests validate when present

Pass `--reproduce-smoke` to `gate` to run the same checks on the exported packet.

## Recommended local workflow

1. `python scripts/materialize_fixtures.py`
2. `pcs-bench verify-fixtures --write` (commit `benchmarks/fixture_manifest.json` when it changes)
3. `pcs-bench validate-cases --suite all --dry-run`
4. `make release-prep`
5. When producers are ready, run `make live-ci` and then `make release-verify`

## Human-readable output

```bash
pcs-bench report --input reports/ci.json --format markdown --out reports/ci.md
pcs-bench compare --old reports/baseline.json --new reports/ci.json
```

See [Interpreting results](interpreting-results.md) and [Metrics](metrics.md).
