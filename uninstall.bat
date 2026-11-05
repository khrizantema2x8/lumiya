@echo off
setlocal EnableDelayedExpansion
title PORTtralica Lumiya v0.5.099.9310 (Pilot) - Environment Uninstaller
cd /d "%~dp0"

echo ========================================================================
echo   PORTtralica Lumiya v0.5.099.9310 (Pilot) - DELTA-AWARE UNINSTALLER
echo ========================================================================
echo.
echo This removes Lumiya's isolated Python dependencies (the .env folder and
echo the "lumiya" conda environment).
echo.
echo Pre-existing system foundations (Git, Miniconda/Anaconda, base Python)
echo and your exported photos in results\ are NEVER touched.
echo.

if exist "%~dp0install_manifest.log" (
    echo --- Package Delta from install_manifest.log ---
    findstr /C:"[ENV]" /C:"[NEW]" "%~dp0install_manifest.log"
    echo -----------------------------------------------
    echo.
)

choice /C YN /M "Proceed with removing Lumiya isolated environment"
if errorlevel 2 exit /b 0

if exist "%~dp0.env" rmdir /s /q "%~dp0.env"

set "CONDA_EXE="
for %%P in (
    "%USERPROFILE%\miniconda3\Scripts\conda.exe"
    "%USERPROFILE%\anaconda3\Scripts\conda.exe"
    "%LOCALAPPDATA%\miniconda3\Scripts\conda.exe"
    "%LOCALAPPDATA%\anaconda3\Scripts\conda.exe"
    "%PROGRAMDATA%\miniconda3\Scripts\conda.exe"
    "%PROGRAMDATA%\anaconda3\Scripts\conda.exe"
    "C:\miniconda3\Scripts\conda.exe"
    "C:\anaconda3\Scripts\conda.exe"
) do (
    if not defined CONDA_EXE (
        if exist "%%~P" set "CONDA_EXE=%%~P"
    )
)

if defined CONDA_EXE (
    "!CONDA_EXE!" env remove -n lumiya -y
) else (
    where conda >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        call conda env remove -n lumiya -y
    )
)

echo.
echo Done. Isolated Lumiya environment removed; pre-existing foundations and results\ preserved.
pause
