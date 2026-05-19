# LabTrust QC Release Benchmark Suite

Benchmarks PCS release-chain integrity and failure localization for the `hospital_lab.qc_release` workflow produced by [LabTrust-Gym](https://github.com/fraware/LabTrust-Gym).

## Cases

| Case | Kind | Expected |
|------|------|----------|
| `labtrust-valid-release-v0` | Valid release | Admitted |
| `labtrust-trace-hash-tamper-v0` | Invalid hash | Rejected at runtime_producer |
| `labtrust-certificate-id-tamper-v0` | Certificate tamper | Rejected |
| `labtrust-legacy-handoff-v0` | Legacy handoff | Rejected |
| `labtrust-missing-qc-result-v0` | Missing QC | Rejected at runtime_producer |
| `labtrust-unauthorized-release-v0` | Unauthorized release | Rejected at runtime_producer |
| `labtrust-stale-trace-v0` | Stale trace after certificate | Rejected at runtime_producer |
| `labtrust-placeholder-commit-v0` | Placeholder commit | Rejected |
| `labtrust-lean-kernel-failure-v0` | Lean theorem failed | Rejected at formal_kernel |

## Run path

1. `pcs validate-release-chain`
2. `labtrust verify-release-protocol`
3. `pf verify science-claim` (when bundle present)
4. Scientific Memory import/render (when available)
