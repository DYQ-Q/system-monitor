@echo off
rem ===================================================================
rem  System Monitor - 启动脚本
rem  双击本文件即可运行图形界面；窗口会保留，若启动报错可看到错误信息。
rem ===================================================================

cd /d "%~dp0"

echo [System Monitor] 正在启动...
uv run system-monitor

if errorlevel 1 (
    echo.
    echo [System Monitor] 启动失败，请检查上面的错误信息。
    echo 可尝试手动执行：uv run system-monitor
    pause
)
