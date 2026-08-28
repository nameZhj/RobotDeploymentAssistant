[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "     VSISLAB 机器人助手 - 正式版单文件 (EXE) 一键打包工具" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host ""

# 1. 检查 Python 环境
Write-Host "[1/3] 检查 Python 环境与依赖库..." -ForegroundColor Yellow
$pyPath = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $pyPath) {
    Write-Host "[错误] 未检测到 Python，请先安装 Python 3.10+ 并添加至系统环境变量 PATH 中。" -ForegroundColor Red
    exit 1
}

$pyVer = & python --version 2>&1
Write-Host "  -> 当前 Python 版本: $pyVer" -ForegroundColor Green

# 2. 检查构建依赖
Write-Host "[2/3] 验证打包所需关键依赖 (pyinstaller, pillow)..." -ForegroundColor Yellow
& python -c "import PyInstaller, PIL" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  -> 正在安装缺失的构建依赖..." -ForegroundColor Magenta
    & python -m pip install -r requirements.txt
}
Write-Host "  -> 依赖检查就绪。" -ForegroundColor Green

# 3. 执行自动化打包
Write-Host "[3/3] 开始编译单文件独立 EXE 程序..." -ForegroundColor Yellow
& python build_package.py

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[错误] 打包过程发生异常，请检查上方日志输出！" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=================================================================" -ForegroundColor Green
Write-Host " 🎉 打包全部完成！仅生成唯一的单文件 EXE：" -ForegroundColor Green
Write-Host "  👉 dist\VSISLAB机器人部署助手.exe" -ForegroundColor White
Write-Host "=================================================================" -ForegroundColor Green
