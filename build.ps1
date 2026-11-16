$ErrorActionPreference = 'Stop'
Write-Host '========================================================' -ForegroundColor Cyan
Write-Host '  ChoreoNexus - 机器人集群编排与部署助手打包脚本' -ForegroundColor Cyan
Write-Host '========================================================'
Write-Host ''

Push-Location $PSScriptRoot
try {
    python -m PyInstaller --noconfirm --clean --windowed `
        --name ChoreoNexus `
        --icon app_icon.ico `
        --add-data 'configs;configs' `
        --add-data 'web;web' `
        --add-data 'preview;preview' `
        --add-data 'assets;assets' `
        --add-data 'backend/models;backend/models' `
        main.py
    if ($LASTEXITCODE -ne 0) {
        Write-Host ''
        Write-Host '[ERROR] 打包失败，请确认已安装 PyInstaller (pip install pyinstaller)。' -ForegroundColor Red
        exit 1
    }
    Write-Host ''
    Write-Host '[SUCCESS] 已生成可执行程序至 dist\ChoreoNexus！' -ForegroundColor Green
} finally {
    Pop-Location
}
