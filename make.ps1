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
    "manifest" { Run "$PcsBench verify-fixtures --write" }
    "test" { Run "$Python -m pytest -q" }
    "bench" { Run "$PcsBench run --suite all --simulate --out reports/latest.json" }
    "ci" {
        Run "$Python -m pip install -e `".[dev]`""
        Run "$Python scripts/materialize_fixtures.py"
        Run "$PcsBench verify-fixtures --write"
        Run "$PcsBench run --suite all --simulate --ci --out reports/ci.json"
        Run "$PcsBench report --input reports/ci.json --format markdown --out reports/ci.md"
    }
    "packet" {
        & $PSScriptRoot/make.ps1 ci
        Run "$PcsBench packet --report reports/ci.json --out packets/latest"
    }
    "html" {
        Run "$PcsBench report --input reports/ci.json --format html --out reports/ci.html"
    }
    default {
        Write-Host @"
Targets: install, fixtures, manifest, test, bench, ci, packet, html
Example: .\make.ps1 ci
"@
    }
}
