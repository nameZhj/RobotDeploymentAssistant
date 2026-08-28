@echo off
chcp 65001 >nul
title VSISLAB 机器人助手 - 正式版单文件打包
echo 正在编译正式版单文件 EXE...
python build_package.py
if errorlevel 1 (
    echo.
    echo [错误] 打包失败，请检查上方日志。
    echo.
    pause
) else (
    echo.
    echo [成功] 正式版单文件构建完成！文件位于: dist\VSISLAB机器人部署助手.exe
    echo.
    pause
)
