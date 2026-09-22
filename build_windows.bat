@echo off
title YAZ adb - Build for Windows
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   YAZ adb — Building Windows version
echo ============================================
echo.

echo [1/4] Installing PyInstaller + Arabic text libs...
py -3 -m pip install --upgrade pyinstaller arabic-reshaper python-bidi 2>nul || python -m pip install --upgrade pyinstaller arabic-reshaper python-bidi

echo [2/4] Building YAZ adb.exe ...
py -3 -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name "YAZ adb" ^
    --add-data "config.json;." ^
    yaz_adb.py 2>nul || python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name "YAZ adb" ^
    --add-data "config.json;." ^
    yaz_adb.py

echo [3/4] Cleaning build cache...
if exist build rmdir /s /q build

echo [4/4] Done.
echo.
echo OUTPUT: dist\YAZ adb.exe
echo.
echo IMPORTANT: copy "YAZ adb.exe" into the tool folder
echo (next to ExynosCli.exe, presets/, data/) and place
echo config.json beside it.
echo.
pause