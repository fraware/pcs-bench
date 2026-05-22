# Windows-friendly Make targets (use when GNU make is awkward with PATH)
param(
    [Parameter(Position = 0)]
    [string]$Target = "help"
)

$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$PcsBench = "$Python -m pcs_bench"

function Run($cmd) {
    Write-Host ">> $cmd"
    Invoke-Expression $cmd
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

switch ($Target) {
    "install" { Run "$Python -m pip install -e `".[dev]`"" }
    "fixtures" { Run "$Python scripts/materialize_fixtures.py" }
    "manifest" {
        Run "$Python scripts/materialize_fixtures.py"
        Run "$PcsBench verify-fixtures --write"
        Run "$PcsBench verify-fixtures"
    }
    "schemas" { Run "$Python scripts/sync_pcs_core_schema.py --pcs-core ../pcs-core" }
    "test" { Run "$Python -m pytest -q" }
    "bench" { Run "$PcsBench run --suite all --simulate --out reports/latest.json" }
    "ci" {
        & $PSScriptRoot/make.ps1 gate
        Run "$PcsBench report --input reports/ci.json --format markdown --out reports/ci.md"
        Run "$PcsBench report --input reports/ci.json --format html --out reports/ci.html"
    }
    "sync-ingest-fixtures" {
        Run "$Python scripts/sync_pcs_core_ingest_fixtures.py --pcs-core ../pcs-core"
    }
    "validate-producer-ingest" {
        Run "$Python scripts/validate_producer_ingest_fixtures.py --pcs-core ../pcs-core"
    }
    "validate-producer-ingest-release" {
        Run "$Python scripts/validate_producer_ingest_fixtures.py --pcs-core ../pcs-core --release-grade"
    }
    "lint" {
        Run "$Python -m ruff check src tests"
    }
    "release-prep" {
        & $PSScriptRoot/make.ps1 install
        & $PSScriptRoot/make.ps1 lint
        & $PSScriptRoot/make.ps1 schemas
        & $PSScriptRoot/make.ps1 validate-producer-ingest-release
        & $PSScriptRoot/make.ps1 test
        & $PSScriptRoot/make.ps1 gate
        & $PSScriptRoot/make.ps1 producer-gate
    }
    "release-verify" {
        & $PSScriptRoot/make.ps1 release-check
    }
    "check-producer-ingests" {
        Run "$PcsBench check-producer-ingests --pcs-core ../pcs-core --labtrust ../LabTrust-Gym --certifyedge ../CertifyEdge --provability-fabric ../provability-fabric --scientific-memory ../scientific-memory"
    }
    "check-producer-ingest-fixtures" {
        Run "$PcsBench check-producer-ingests --fixtures-only --pcs-core ../pcs-core"
    }
    "producer-gate" {
        & $PSScriptRoot/make.ps1 install
        Run "$PcsBench gate --suite all --run-producer-benchmarks --use-producer-fixtures --reproduce-smoke --out reports/producer-gate.json --out-packet packets/producer-gate"
    }
    "producer-gate-live" {
        & $PSScriptRoot/make.ps1 install
        Run "$PcsBench gate --suite all --live --run-producer-benchmarks --use-producer-fixtures --reproduce-smoke --out reports/producer-gate.json --out-packet packets/producer-gate --pcs-core ../pcs-core --labtrust ../LabTrust-Gym --certifyedge ../CertifyEdge --provability-fabric ../provability-fabric --scientific-memory ../scientific-memory"
    }
    "producer-gate-release" { & $PSScriptRoot/make.ps1 live-ci }
    "live-ci" {
        & $PSScriptRoot/make.ps1 install
        Run "$Python scripts/sync_pcs_core_schema.py --pcs-core ../pcs-core"
        Run "$PcsBench producer-doctor --json-out reports/producer-doctor.json --pcs-core ../pcs-core --labtrust ../LabTrust-Gym --certifyedge ../CertifyEdge --provability-fabric ../provability-fabric --scientific-memory ../scientific-memory --release-grade; if ($LASTEXITCODE -ne 0) { Write-Host 'producer-doctor: not all producers ready (continuing)' }"
        Run "$PcsBench check-producer-ingests --release-grade --pcs-core ../pcs-core --labtrust ../LabTrust-Gym --certifyedge ../CertifyEdge --provability-fabric ../provability-fabric --scientific-memory ../scientific-memory"
        Run "$PcsBench gate --suite all --live --run-producer-benchmarks --reproduce-smoke --out reports/live-ci.json --out-packet packets/live-ci --pcs-core ../pcs-core --labtrust ../LabTrust-Gym --certifyedge ../CertifyEdge --provability-fabric ../provability-fabric --scientific-memory ../scientific-memory"
    }
    "release-check" {
        & $PSScriptRoot/make.ps1 install
        Run "$PcsBench release-readiness --strict --pcs-core ../pcs-core --labtrust ../LabTrust-Gym --certifyedge ../CertifyEdge --provability-fabric ../provability-fabric --scientific-memory ../scientific-memory --live-ci-report reports/live-ci.json --live-ci-packet packets/live-ci --json-out reports/release-readiness.json"
    }
    "producer-doctor" {
        Run "$PcsBench producer-doctor --json-out reports/producer-doctor.json --pcs-core ../pcs-core --labtrust ../LabTrust-Gym --certifyedge ../CertifyEdge --provability-fabric ../provability-fabric --scientific-memory ../scientific-memory; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }"
    }
    "gate" {
        & $PSScriptRoot/make.ps1 install
        Run "$PcsBench gate --out reports/ci.json --out-packet packets/latest --reproduce-smoke"
    }
    "packet" {
        & $PSScriptRoot/make.ps1 ci
    }
    "html" {
        Run "$PcsBench report --input reports/ci.json --format html --out reports/ci.html"
    }
    default {
        Write-Host @"
Targets: install, fixtures, manifest, schemas, lint, test, bench, ci, gate, producer-gate, release-prep, live-ci, release-verify, release-check, producer-doctor, check-producer-ingests, validate-producer-ingest-release, sync-ingest-fixtures, packet, html
Example: .\make.ps1 gate
"@
    }
}
