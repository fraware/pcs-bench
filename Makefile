# Use python -m pcs_bench so targets work when the console script is not on PATH (common on Windows).
PYTHON ?= python
PCS_BENCH = $(PYTHON) -m pcs_bench

.PHONY: install test bench ci gate producer-gate producer-gate-live producer-gate-release live-ci release-check producer-doctor fixtures manifest packet schemas lint clean validate-producer-ingest sync-ingest-fixtures check-producer-ingests check-producer-ingest-fixtures

install:
	$(PYTHON) -m pip install -e ".[dev]"

fixtures:
	$(PYTHON) scripts/materialize_fixtures.py

manifest: fixtures
	$(PCS_BENCH) verify-fixtures --write
	$(PCS_BENCH) verify-fixtures

schemas:
	$(PYTHON) scripts/sync_pcs_core_schema.py --pcs-core ../pcs-core

test:
	$(PYTHON) -m pytest -q

bench:
	$(PCS_BENCH) run --suite all --simulate --out reports/latest.json

ci: gate
	$(PCS_BENCH) report --input reports/ci.json --format markdown --out reports/ci.md
	$(PCS_BENCH) report --input reports/ci.json --format html --out reports/ci.html

sync-ingest-fixtures:
	$(PYTHON) scripts/sync_pcs_core_ingest_fixtures.py --pcs-core ../pcs-core

validate-producer-ingest:
	$(PYTHON) scripts/validate_producer_ingest_fixtures.py --pcs-core ../pcs-core

validate-producer-ingest-release:
	$(PYTHON) scripts/validate_producer_ingest_fixtures.py --pcs-core ../pcs-core --release-grade

check-producer-ingests:
	$(PCS_BENCH) check-producer-ingests \
		--pcs-core ../pcs-core \
		--labtrust ../LabTrust-Gym \
		--certifyedge ../CertifyEdge \
		--provability-fabric ../provability-fabric \
		--scientific-memory ../scientific-memory

check-producer-ingest-fixtures:
	$(PCS_BENCH) check-producer-ingests --fixtures-only --pcs-core ../pcs-core

producer-gate: install
	$(PCS_BENCH) gate --suite all --run-producer-benchmarks --use-producer-fixtures --reproduce-smoke \
		--out reports/producer-gate.json --out-packet packets/producer-gate

producer-gate-hybrid: install
	$(PCS_BENCH) gate --suite all --hybrid --run-producer-benchmarks --reproduce-smoke \
		--out reports/producer-gate.json --out-packet packets/producer-gate \
		--pcs-core ../pcs-core \
		--labtrust ../LabTrust-Gym \
		--certifyedge ../CertifyEdge \
		--provability-fabric ../provability-fabric \
		--scientific-memory ../scientific-memory

producer-gate-live: install
	$(PCS_BENCH) gate --suite all --live --run-producer-benchmarks --use-producer-fixtures --reproduce-smoke \
		--out reports/producer-gate.json --out-packet packets/producer-gate \
		--pcs-core ../pcs-core \
		--labtrust ../LabTrust-Gym \
		--certifyedge ../CertifyEdge \
		--provability-fabric ../provability-fabric \
		--scientific-memory ../scientific-memory

producer-gate-release: live-ci

live-ci: install schemas
	-$(PCS_BENCH) producer-doctor --json-out reports/producer-doctor.json \
		--pcs-core ../pcs-core \
		--labtrust ../LabTrust-Gym \
		--certifyedge ../CertifyEdge \
		--provability-fabric ../provability-fabric \
		--scientific-memory ../scientific-memory \
		--release-grade
	$(PCS_BENCH) check-producer-ingests --release-grade \
		--pcs-core ../pcs-core \
		--labtrust ../LabTrust-Gym \
		--certifyedge ../CertifyEdge \
		--provability-fabric ../provability-fabric \
		--scientific-memory ../scientific-memory
	$(PCS_BENCH) gate --suite all --live --run-producer-benchmarks --reproduce-smoke \
		--out reports/live-ci.json --out-packet packets/live-ci \
		--pcs-core ../pcs-core \
		--labtrust ../LabTrust-Gym \
		--certifyedge ../CertifyEdge \
		--provability-fabric ../provability-fabric \
		--scientific-memory ../scientific-memory

release-check: install
	$(PCS_BENCH) release-readiness --strict \
		--pcs-core ../pcs-core \
		--labtrust ../LabTrust-Gym \
		--certifyedge ../CertifyEdge \
		--provability-fabric ../provability-fabric \
		--scientific-memory ../scientific-memory \
		--live-ci-report reports/live-ci.json \
		--live-ci-packet packets/live-ci \
		--json-out reports/release-readiness.json

producer-doctor:
	-$(PCS_BENCH) producer-doctor --json-out reports/producer-doctor.json \
		--pcs-core ../pcs-core \
		--labtrust ../LabTrust-Gym \
		--certifyedge ../CertifyEdge \
		--provability-fabric ../provability-fabric \
		--scientific-memory ../scientific-memory

gate: install
	$(PCS_BENCH) gate --out reports/ci.json --out-packet packets/latest --reproduce-smoke

packet: ci
	$(PCS_BENCH) packet --report reports/ci.json --out packets/latest
	$(PCS_BENCH) verify-packet --packet packets/latest --reproduce-smoke

lint:
	$(PYTHON) -m ruff check src tests

clean:
	-$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').glob('.pytest_cache')]"
	-$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').glob('*.egg-info')]"
	-$(PYTHON) -c "import shutil; shutil.rmtree('dist', ignore_errors=True); shutil.rmtree('build', ignore_errors=True)"
