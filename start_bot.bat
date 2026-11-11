@echo off
chcp 65001 > nul
title Telegram AI Bot
echo ====================================================
echo        Telegram AI Bot ishga tushmoqda...
echo ====================================================
echo.

set "PY_EXE=python"
where python >nul 2>nul
if %errorlevel% neq 0 (
    set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)

echo [1/2] Kutubxonalar tekshirilmoqda...
"%PY_EXE%" -m pip install -r requirements.txt

echo.
echo [2/2] Bot ishga tushirilmoqda...
"%PY_EXE%" bot.py

if %errorlevel% neq 0 (
    echo.
    echo ----------------------------------------------------
    echo Xatolik yuz berdi!
    echo ----------------------------------------------------
)
pause
