$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $RepoRoot
try {
    Write-Host "=== [1/4] Auditing Hygiene & Syncing Hydrogen High INDEX.md ===" -ForegroundColor Cyan
    python ai_execution_plan/verify_deep_closure.py
    if ($LASTEXITCODE -ne 0) { throw "Hygiene check failed." }

    Write-Host "=== [2/4] Running Lower Computer Unit Tests ===" -ForegroundColor Cyan
    python -m pytest -q lower_computer/tests
    if ($LASTEXITCODE -ne 0) { throw "Lower computer tests failed." }

    Write-Host "=== [3/4] Running Upper Computer Unit & Regression Tests ===" -ForegroundColor Cyan
    python -m pytest -q upper_computer/tests
    if ($LASTEXITCODE -ne 0) { throw "Upper computer tests failed." }

    Write-Host "=== [4/4] Running Dual-Computer E2E Closed-Loop Tests ===" -ForegroundColor Cyan
    python -m pytest -q ai_execution_plan/test_dual_computer_e2e.py
    if ($LASTEXITCODE -ne 0) { throw "Dual-computer E2E tests failed." }

    Write-Host "[ALL PASS] Upper + Lower + Dual E2E Closure Verified!" -ForegroundColor Green
} finally {
    Pop-Location
}
