# Live release gate

Simulation is the default developer path. The **credible** PCS benchmark is **live mode**: real CLIs from pcs-core, LabTrust-Gym, CertifyEdge, provability-fabric, and scientific-memory.

## LabTrust release gate

Suites with `live_required_for_release: true` (LabTrust QC release) require at least one case executed live when `--ci` is set.

```bash
pcs-bench check-adapters --pcs-core ../pcs-core --labtrust ../LabTrust-Gym
pcs-bench run --suite labtrust-qc-release --live --ci --out reports/live-labtrust.json
pcs-bench validate-report --input reports/live-labtrust.json --schema-source ../pcs-core
```

CI fails when:

- `execution_mode` is not `live` and `live_cases` is 0 for a live-required suite
- Report does not validate against `BenchmarkReport.v0`
- Thresholds or valid/invalid release rules fail

## Progressive live rollout

| Stage | Command |
|-------|---------|
| 1 | `run --suite labtrust-qc-release --live --ci` |
| 2 | `run --suite tool-use-safety --live --ci` |
| 3 | `run --suite computation-reproducibility --live --ci` |
| 4 | `run --suite all --live --ci` |

Mark additional suites with `live_required_for_release: true` in `suite.yaml` when their CLIs are stable in CI.

## GitHub Actions

The default PR pipeline runs **simulate-gate** only (no sibling repos required).

To run the live LabTrust gate manually:

1. Open **Actions** → **PCS Benchmark** → **Run workflow**
2. Enable **Run LabTrust live gate**
3. Ensure workflow can check out `SentinelOps-CI/pcs-core` and `fraware/LabTrust-Gym` (public repos) and that CLIs are installable on the runner

For private monorepos, use a self-hosted runner with sibling repos at fixed paths and the same commands as local development.

## Hybrid fallback

`--hybrid` tries live CLIs first; if all commands exit 127 (CLI missing), it falls back to fixture sidecars. Hybrid fallback cases are counted separately in the report (`hybrid_fallback_cases`). They do **not** satisfy the live release gate.
