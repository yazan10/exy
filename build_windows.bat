@echo off
title YAZ adb - Hardened single-file build
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   YAZ adb — Hardened build (one-file)
echo   All files (config + presets + data +
echo   ExynosCli.exe + DLLs) are EMERGED INSIDE
echo   the exe and AES-encrypted.
echo ============================================
echo.
echo Choose build target:
echo   [1] Normal build  (config.json)
echo   [2] Admin build   (config_admin.json)
set /p TGT=Your choice (1 or 2):
if "%TGT%"=="2" (
    set MODE=admin
) else (
    set MODE=normal
)
echo.
echo Building %MODE% version...
echo.

echo [1/1] Running build_hardened.py ...
py -3 build_hardened.py %MODE% 2>nul || python build_hardened.py %MODE% 2>nul || python3 build_hardened.py %MODE%
if errorlevel 1 (
    echo.
    echo BUILD FAILED — make sure engine files exist one folder above
    echo (ExynosCli.exe, DLLs, presets/, data/) and PyInstaller 5.x
    echo is installed:  pip install "pyinstaller==5.13.2" tinyaes pycryptodome
    pause
    exit /b 1
)

echo.
echo OUTPUT: dist_hardened\*.exe
echo.
echo This exe is fully self-contained and encrypted.
echo No external files needed — just run it.
pause