param(
    [string]$ProjectRoot = ".",
    [string[]]$CompileTargets = @("src"),
    [string[]]$TestTargets = @("tests/unit"),
    [switch]$SkipTests
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path $ProjectRoot).Path
Push-Location $Root
try {
    Write-Host "=== Stage Director task validation ===" -ForegroundColor Cyan
    python --version
    if ($LASTEXITCODE -ne 0) { throw 'Python unavailable.' }
    foreach ($target in $CompileTargets) {
        if (Test-Path $target) {
            Write-Host "[COMPILE] $target" -ForegroundColor Yellow
            python -m compileall -q $target
            if ($LASTEXITCODE -ne 0) { throw "Compile failed: $target" }
        }
    }
    if (-not $SkipTests) {
        foreach ($target in $TestTargets) {
            if (Test-Path $target) {
                Write-Host "[PYTEST] $target" -ForegroundColor Yellow
                python -m pytest -q $target
                if ($LASTEXITCODE -ne 0) { throw "Tests failed: $target" }
            }
        }
    }
    git diff --check
    if ($LASTEXITCODE -ne 0) { throw 'git diff --check failed.' }
    git status --short
    git diff --stat
    if (-not (Test-Path 'scripts/stage_director_guard.py')) { throw 'stage_director_guard.py missing.' }
    python scripts/stage_director_guard.py verify --root $Root
    if ($LASTEXITCODE -ne 0) { throw 'Guard failed. Do not recapture baseline.' }
    Write-Host '[PASS] Validation completed.' -ForegroundColor Green
} finally { Pop-Location }
