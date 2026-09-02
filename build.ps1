Write-Host '========================================================' -ForegroundColor Cyan
Write-Host '  VSISLAB Robot Deployment Assistant - Packaging EXE' -ForegroundColor Cyan
Write-Host '========================================================'
Write-Host ''
python build_package.py
if ( -ne 0) {
    Write-Host ''
    Write-Host '[ERROR] Packaging failed.' -ForegroundColor Red
    Write-Host ''
    Read-Host 'Press Enter to exit'
    exit 1
} else {
    Write-Host ''
    Write-Host '[SUCCESS] Standalone EXE created successfully in dist folder.' -ForegroundColor Green
    Write-Host ''
    Read-Host 'Press Enter to exit'
}
