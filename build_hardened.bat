@echo off
title YAZ adb - Hardened single-file build
chcp 65001 >nul
cd /d "%~dp0"

setlocal EnableDelayedExpansion

rem ============================================================
rem  YAZ adb - Hardened build (all files INSIDE one exe)
rem  Runs PyInstaller --onefile --windowed --key <AES>
rem  Embedding: config.json + ExynosCli.exe + DLLs + presets + data
rem ============================================================

echo Choose build target:
echo   [1] Normal build   (config.json)
echo   [2] Admin build    (config_admin.json - protected)
set /p TGT=Your choice (1 or 2): 

if "%TGT%"=="2" (
    set APPNAME=YAZ adb ADMIN
    set SRC=config_admin.json
) else (
    set APPNAME=YAZ adb
    set SRC=config.json
)

echo.
echo ============================================
echo   Building "%APPNAME%" — one-file hardened
echo ============================================
echo.

set STAGE=%TEMP%\yazadb_stage_%RANDOM%
set OUTROOT=dist_hardened

echo [1/6] Staging bundle folder...
set TOOLROOT=%~dp0..\..
if not exist "%TOOLROOT%\ExynosCli.exe" (
    echo ERROR: ExynosCli.exe not found in "%TOOLROOT%"
    pause
    exit /b 1
)
rmdir /s /q "%STAGE%" 2>nul
mkdir "%STAGE%"
copy /y "%TOOLROOT%\ExynosCli.exe" "%STAGE%\" >nul
for %%F in (%TOOLROOT%\*.dll) do copy /y "%%F" "%STAGE%\" >nul
xcopy /e /q /y "%TOOLROOT%\presets" "%STAGE%\presets\" >nul
xcopy /e /q /y "%TOOLROOT%\data" "%STAGE%\data\" >nul
echo     staged %STAGE%

echo [2/6] Installing PyInstaller if needed...
py -3 -m pip install --upgrade pyinstaller 2>nul || python -m pip install --upgrade pyinstaller

echo [3/6] Copying chosen config as embedded config.json...
copy /y "%SRC%" "%STAGE%\config.json" >nul

echo [4/6] Building "%APPNAME%.exe" with AES key...
if not exist "%OUTROOT%" mkdir "%OUTROOT%"
py -3 -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name "%APPNAME%" ^
    --key "YAZ-ADB-H7G3X9KQ-MN2P4WVZ-B8C6D1F0-5A7E9J3L" ^
    --paths "%STAGE%" ^
    --add-data "%STAGE%\config.json;." ^
    --add-binary "%STAGE%\ExynosCli.exe;." ^
    --add-binary "%STAGE%\archive.dll;." ^
    --add-binary "%STAGE%\Basic.dll;." ^
    --add-binary "%STAGE%\drvman.dll;." ^
    --add-binary "%STAGE%\exynos.dll;." ^
    --add-binary "%STAGE%\libcrypto-1_1x64vc143.dll;." ^
    --add-binary "%STAGE%\libssl-1_1x64vc143.dll;." ^
    --add-binary "%STAGE%\libusb-1.0.dll;." ^
    --add-binary "%STAGE%\Qt5Core.dll;." ^
    --add-binary "%STAGE%\zlib1x64vc143.dll;." ^
    --add-data "%STAGE%\presets;presets" ^
    --add-data "%STAGE%\data;data" ^
    --distpath "%OUTROOT%" ^
    --workpath build_hardened ^
    --specpath build_hardened ^
    yaz_adb.py 2>nul || python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name "%APPNAME%" ^
    --key "YAZ-ADB-H7G3X9KQ-MN2P4WVZ-B8C6D1F0-5A7E9J3L" ^
    --paths "%STAGE%" ^
    --add-data "%STAGE%\config.json;." ^
    --add-binary "%STAGE%\ExynosCli.exe;." ^
    --add-binary "%STAGE%\archive.dll;." ^
    --add-binary "%STAGE%\Basic.dll;." ^
    --add-binary "%STAGE%\drvman.dll;." ^
    --add-binary "%STAGE%\exynos.dll;." ^
    --add-binary "%STAGE%\libcrypto-1_1x64vc143.dll;." ^
    --add-binary "%STAGE%\libssl-1_1x64vc143.dll;." ^
    --add-binary "%STAGE%\libusb-1.0.dll;." ^
    --add-binary "%STAGE%\Qt5Core.dll;." ^
    --add-binary "%STAGE%\zlib1x64vc143.dll;." ^
    --add-data "%STAGE%\presets;presets" ^
    --add-data "%STAGE%\data;data" ^
    --distpath "%OUTROOT%" ^
    --workpath build_hardened ^
    --specpath build_hardened ^
    yaz_adb.py

echo [5/6] Cleaning build cache...
if exist build_hardened rmdir /s /q build_hardened
rmdir /s /q "%STAGE%" 2>nul

echo [6/6] Done.
echo.
echo OUTPUT: %OUTROOT%\%APPNAME%.exe
echo.
echo This exe is self-contained: config + presets + data + ExynosCli.exe
echo are embedded and encrypted with an AES key.
echo.
pause