@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
    python main.py
) else (
    where py >nul 2>nul
    if %errorlevel%==0 (
        py main.py
    ) else (
        echo [ERROR] Python not found. Please install Python 3.8+ and PyQt5.
        pause
    )
)
