Write-Host '========================================================' -ForegroundColor Cyan
Write-Host '  VSISLAB 机器人部署助手 - 中文安装向导打包工具' -ForegroundColor Cyan
Write-Host '========================================================'
Write-Host ''
python build_package.py
if ($LASTEXITCODE -ne 0) {
    Write-Host ''
    Write-Host '[ERROR] 打包失败，请检查上方控制台日志。' -ForegroundColor Red
    Write-Host ''
    Read-Host 'Press Enter to exit'
    exit 1
} else {
    Write-Host ''
    Write-Host '[SUCCESS] 中文安装向导已成功生成至 dist 目录！' -ForegroundColor Green
    Write-Host ''
    Read-Host 'Press Enter to exit'
}
