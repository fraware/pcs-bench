# pcs-bench documentation

pcs-bench evaluates Proof-Carrying Science (PCS) releases by running benchmark cases and aggregating results from producer repositories. It does not define PCS schemas or run admission logic itself.

## Start here

| Guide | When to read it |
|-------|-----------------|
| [Release guide](release.md) | Tagging a PCS ecosystem release; artifacts and checklist |
| [Running benchmarks](execution.md) | Daily use: simulate vs live, gates, CI, packets |
| [Producer integration](producers.md) | Wiring LabTrust-Gym, CertifyEdge, provability-fabric, scientific-memory |

## Reference

| Topic | Document |
|-------|----------|
| Architecture (contributors) | [architecture.md](architecture.md) |
| Eight benchmark metrics | [metrics.md](metrics.md) |
| Status fields and evidence levels | [benchmark-vocabulary.md](benchmark-vocabulary.md) |
| Methodology and suite layout | [benchmark-methodology.md](benchmark-methodology.md) |
| Reading reports | [interpreting-results.md](interpreting-results.md) |
| Adding a suite | [adding-a-benchmark-suite.md](adding-a-benchmark-suite.md) |

## Quick commands

```bash
pip install -e ".[dev]"
make release-prep    # offline: lint, test, gate, producer-gate
make live-ci         # live release (sibling repos required)
make release-verify  # after live-ci
```

On Windows use `.\make.ps1 gate` instead of `make gate`.
