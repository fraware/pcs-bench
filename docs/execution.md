# Running benchmarks

## Execution modes

| Mode | Flag | When to use |
|------|------|-------------|
| Simulate | `--simulate` (default) | Local development and CI without installing producer CLIs |
| Live | `--live` | Release evaluation against real command-line tools |
| Hybrid | `--hybrid` | Try live first; fall back to expected outcome files if a CLI is missing |
| Dry run | `--dry-run` | Plan a run without executing external commands |

Reports record `execution_mode` and `evidence_grade`:

- **release** — `--ci` and `--live` together; used for credible release evidence
- **developer** — simulate or hybrid; fine for development, not sufficient alone for release

Suites marked `live_required_for_release: true` in `suite.yaml` fail CI when run in simulate mode with zero live cases.

## Standard offline gate

Runs without sibling repositories:

```bash
make gate
# equivalent:
pcs-bench gate --out reports/ci.json --out-packet packets/latest --reproduce-smoke
```

Steps: materialize fixtures, verify fixture manifest, validate cases, validate reference producer ingests, run all suites in simulate mode with CI thresholds, validate report schema, export packet, verify packet (including reproduction smoke).

## Producer offline gate

Includes pcs-bench suites plus four producer ingests (reference data allowed):

```bash
make producer-gate
```

Uses `--run-producer-benchmarks --use-producer-fixtures`. Do not combine `--live` with `--use-producer-fixtures`; the gate rejects that combination.

## Live release gate

```bash
make live-ci
```

Runs `producer-doctor`, `check-producer-ingests --release-grade`, then:

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

Check adapters before live runs:

```bash
pcs-bench check-adapters --pcs-core ../pcs-core --labtrust ../LabTrust-Gym
```

## CI failure conditions

With `--ci`, the run exits non-zero when:

- A valid release case is rejected (`valid_release_rejected`)
- An invalid release case is admitted (`invalid_release_not_detected`)
- A measured metric score is below its threshold in `pcs-bench.yaml`
- A required metric could not be measured (`failed_to_measure`)
- The report fails `BenchmarkReport.v0` validation
- A live-required suite ran with zero live cases while not in live mode

Optional metrics with `insufficient_cases` do not fail CI unless listed under `required_metrics` for that suite.

## Packets and reproduction smoke

```bash
pcs-bench packet --report reports/ci.json --out packets/latest
pcs-bench verify-packet --packet packets/latest --reproduce-smoke
```

Reproduction smoke writes `packet_reproduction_report.v0.json` into the packet directory. It checks that one valid and one invalid case reproduce expected outcomes, that explain-quality JSON validates, and that scientific-memory rendering includes required sections.

Pass `--reproduce-smoke` to `gate` to run the same checks on the exported packet.

## Recommended local pipeline

1. `python scripts/materialize_fixtures.py`
2. `pcs-bench verify-fixtures --write` (commit `benchmarks/fixture_manifest.json` when changed)
3. `pcs-bench validate-cases --suite all --dry-run`
4. `make gate`
5. `pytest -q`
6. When producers are ready: `make live-ci` then `make release-check`

## Human-readable output

```bash
pcs-bench report --input reports/ci.json --format markdown --out reports/ci.md
pcs-bench compare --old reports/baseline.json --new reports/ci.json
```

See [Interpreting results](interpreting-results.md) and [Metrics](metrics.md).
