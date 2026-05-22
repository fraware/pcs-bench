# Configuration

pcs-bench reads `pcs-bench.yaml` from the repository root, or from a path passed with `--config`. Generate a starter file with the following command.

```bash
pcs-bench init
```

CLI flags such as `--pcs-core`, `--labtrust`, and `--live` override the file for a single run.

## Repository paths

Point each key at a local clone of the ecosystem repository.

```yaml
repos:
  pcs_core: ../pcs-core
  labtrust: ../LabTrust-Gym
  certifyedge: ../CertifyEdge
  provability_fabric: ../provability-fabric
  scientific_memory: ../scientific-memory
```

Live gates and `producer-doctor` use these paths to resolve producer ingests and CLIs. Offline `gate` and `release-prep` complete with only this repository present.

## Command names

Override executable names when tools are missing from PATH.

```yaml
commands:
  pcs: pcs
  labtrust: labtrust
  certifyedge: certifyedge
  pf: pf
  just: just
```

## CI thresholds

When you pass `--ci`, measured metric scores must meet these minimums (0.0–1.0).

```yaml
thresholds:
  release_reproducibility_score: 0.95
  failure_localization_accuracy: 0.90
  certificate_completeness_score: 0.95
  registry_coverage_score: 0.95
  formal_check_coverage_score: 0.90
  scientific_memory_interpretability_score: 0.95
  repair_hint_quality_score: 0.90
  cross_domain_portability_score: 0.90
```

Definitions appear in [Metrics](metrics.md). Suites can mark metrics as optional in `suite.yaml`.

## Workspace and timeouts

```yaml
workspace:
  root: .pcs-bench-workspaces
  clean_between_cases: true
  preserve_failed_cases: true

execution:
  parallel_cases: 1

timeouts:
  command_seconds: 120
  suite_seconds: 1800
```

Increase `parallel_cases` in simulate mode for faster offline runs.

## Per-suite policy

Each `benchmarks/<suite>/suite.yaml` can declare `required_metrics`, `optional_metrics`, and `live_required_for_release`. See [Running benchmarks](execution.md) and [Adding a benchmark suite](adding-a-benchmark-suite.md).
