param(
    [string]$ProjectRoot = ".",
    [string[]]$CompileTargets = @("src", "backend"),
    [string[]]$TestTargets = @("tests"),
    [switch]$SkipTests
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path $ProjectRoot).Path
Push-Location $Root
try {
    Write-Host "=== ChoreoNexus Task Validation ===" -ForegroundColor Cyan
    python --version
    if ($LASTEXITCODE -ne 0) { throw 'Python unavailable.' }

    foreach ($target in $CompileTargets) {
        if (Test-Path $target) {
            Write-Host "[COMPILE] $target" -ForegroundColor Yellow
            python -m compileall -q $target
            if ($LASTEXITCODE -ne 0) { throw "Compile failed: $target" }
        }
    }

    if (Test-Path 'scripts/verify_hygiene.py') {
        Write-Host "[HYGIENE] scripts/verify_hygiene.py" -ForegroundColor Yellow
        python scripts/verify_hygiene.py
        if ($LASTEXITCODE -ne 0) { throw 'Hygiene verification failed.' }
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
    Write-Host '[PASS] Validation completed.' -ForegroundColor Green
} finally {
    Pop-Location
}
