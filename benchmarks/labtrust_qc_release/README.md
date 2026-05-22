# LabTrust QC release benchmark suite

This suite benchmarks PCS release-chain integrity and failure localization for the `hospital_lab.qc_release` workflow from [LabTrust-Gym](https://github.com/fraware/LabTrust-Gym).

## Cases

| Case | Kind | Expected system outcome |
|------|------|-------------------------|
| `labtrust-valid-release-v0` | Valid release | Admitted |
| `labtrust-trace-hash-tamper-v0` | Invalid hash | Rejected (runtime producer) |
| `labtrust-certificate-id-tamper-v0` | Certificate tamper | Rejected |
| `labtrust-legacy-handoff-v0` | Legacy handoff | Rejected |
| `labtrust-missing-qc-result-v0` | Missing QC | Rejected (runtime producer) |
| `labtrust-unauthorized-release-v0` | Unauthorized release | Rejected (runtime producer) |
| `labtrust-stale-trace-v0` | Stale trace after certificate | Rejected (runtime producer) |
| `labtrust-placeholder-commit-v0` | Placeholder commit | Rejected |
| `labtrust-lean-kernel-failure-v0` | Lean check failed | Rejected (formal kernel) |

## Evaluation path

For live runs, the harness typically invokes `pcs validate-release-chain`, then `labtrust verify-release-protocol`, then `pf verify science-claim` when a bundle is present, and finally Scientific Memory import and render when configured.

Run this suite locally.

```bash
pcs-bench run --suite labtrust-qc-release --simulate --out reports/labtrust.json
pcs-bench run --suite labtrust-qc-release --live --ci --out reports/labtrust-live.json
```

Further suite documentation lives in [docs/benchmark-methodology.md](../../docs/benchmark-methodology.md).
