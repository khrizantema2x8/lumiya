@echo off
setlocal EnableDelayedExpansion
title PORTtralica Lumiya v0.6.073.8820 (Pilot) - Uninstaller
cd /d "%~dp0"

set "MODE=MANIFEST"
set "CONFIRM="

:parse_args
if "%~1"=="" goto after_args
if /I "%~1"=="-h" goto show_help
if /I "%~1"=="--help" goto show_help
if /I "%~1"=="/h" goto show_help
if /I "%~1"=="/?" goto show_help
if /I "%~1"=="/purge" set "MODE=PURGE"
if /I "%~1"=="--purge" set "MODE=PURGE"
if /I "%~1"=="-p" set "MODE=PURGE"
if /I "%~1"=="purge" set "MODE=PURGE"
if /I "%~1"=="/manifest" set "MODE=MANIFEST"
if /I "%~1"=="--manifest" set "MODE=MANIFEST"
if /I "%~1"=="-m" set "MODE=MANIFEST"
if /I "%~1"=="/y" set "CONFIRM=1"
if /I "%~1"=="-y" set "CONFIRM=1"
if /I "%~1"=="--yes" set "CONFIRM=1"
shift
goto parse_args

:show_help
echo ========================================================================
echo   PORTtralica Lumiya v0.6.073.8820 (Pilot) - UNINSTALLER REFERENCE
echo ========================================================================
echo.
echo Usage: uninstall.bat [OPTIONS]
echo.
echo Options:
echo   --uninstall, -u       Remove this program footprint dependencies (default: manifest cleanup)
echo   --purge, -p, /purge   Thoroughly purge runtime pillars
echo   -y, --yes, /y         Skip interactive confirmations
echo   -h, --help, /?        Display this help reference
echo.
echo Default Mode (without --purge):
echo   Performs manifest-based cleanup: removes this program footprint dependencies
echo   (.env and Conda 'lumiya' environment) while keeping user configurations
echo   (user\) and exported photos (results\) safe.
echo.
echo Note:
echo   The program folder itself is ALWAYS kept intact so you can manage,
echo   back up, or delete remaining files at your discretion.
exit /b 0

:after_args
chcp 65001 >nul 2>&1
for /F %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "LOGO_GOLD=%ESC%[38;2;243;214;137m"
set "DIM=%ESC%[90m"
set "GREEN=%ESC%[92m"
set "YELLOW=%ESC%[93m"
set "RED=%ESC%[91m"
set "CYAN=%ESC%[96m"
set "RESET=%ESC%[0m"

cls
echo.
echo   %LOGO_GOLD%              :::::::::::::                                                                         %RESET%
echo   %LOGO_GOLD%              :   :::::::::                                                                         %RESET%
echo   %LOGO_GOLD%                :::                                            :::                                  %RESET%
echo   %LOGO_GOLD%               ::                                              :::                                  %RESET%
echo   %LOGO_GOLD%              ::   :::       ::    ::  ::::::   ::::::       ::       ::::    :::      ::::::::     %RESET%
echo   %LOGO_GOLD%            :::   ::       :::     :::::   :: :::   ::     :::      :::      ::::   ::::      : :   %RESET%
echo   %LOGO_GOLD%           ::    ::       ::     ::::      :::     ::     :::      ::       ::::  :::        ::::   %RESET%
echo   %LOGO_GOLD%         :::    ::      :::    :::        ::      ::     ::      :::       :::   ::        :::    ::%RESET%
echo   %LOGO_GOLD%:::::   ::     ::    :::::   :::        :::     ::    ::::    :::::      :::  :::::     ::::    ::: %RESET%
echo   %LOGO_GOLD%:    :::       ::::::  ::::::::        ::       ::::::  :::::::  :::::::::::::   :::::::::::::::    %RESET%
echo   %LOGO_GOLD% ::::::::       ::                                                     ::::                         %RESET%
echo   %LOGO_GOLD%        :::::   ::                                                 ::::::                           %RESET%
echo   %LOGO_GOLD%            :::::                                                :::::::                            %RESET%
echo   %LOGO_GOLD%                                                              :::: :::                              %RESET%
echo   %LOGO_GOLD%                                                             ::: ::::                               %RESET%
echo   %LOGO_GOLD%                                                             ::::::                                 %RESET%
echo.
echo   %DIM%PORTtralica Lumiya v0.6.073.8820 (Pilot) - UNINSTALLER%RESET%
echo   ====================================================================================================
echo.

set "MANIFEST_PATH=%~dp0user\install_manifest.log"
if not exist "%MANIFEST_PATH%" if exist "%~dp0install_manifest.log" set "MANIFEST_PATH=%~dp0install_manifest.log"

if "%MODE%"=="PURGE" (
    echo   ====================================================================================================
    echo   [%RED%WARNING // THOROUGH PURGE SELECTED%RESET%]
    echo   This will PERMANENTLY purge all runtime pillars:
    echo     - Conda environment 'lumiya' and local .env
    echo     - Pip/Conda package caches and temporary runtime data
    echo.
    echo   The program folder itself and your exported photos ^(results\^)
    echo   are ALWAYS KEPT intact.
    echo   Pre-existing system foundations ^(Git, Miniconda, base Python^) stay intact.
    echo   ====================================================================================================
    echo.
    if not defined CONFIRM (
        choice /C YN /M "  Are you sure you want to purge all runtime environments and caches"
        if errorlevel 2 (
            echo   Uninstallation aborted.
            exit /b 0
        )
    )
    echo.
    echo   [%YELLOW%5-SECOND SAFETY COUNTDOWN%RESET%] Press Ctrl+C to cancel if this was chosen by mistake...
    timeout /t 5
) else (
    echo   [%CYAN%MANIFEST CLEANUP // DEFAULT MODE%RESET%]
    echo   Removing Lumiya's isolated dependencies ^(.env and Conda 'lumiya' environment^).
    echo   User configurations ^(user\^) and exported photos ^(results\^) will be KEPT.
    if exist "%MANIFEST_PATH%" (
        echo.
        echo   --- Recorded Delta from install_manifest.log ---
        findstr /C:"[ENV]" /C:"[NEW]" "%MANIFEST_PATH%" 2>nul
        echo   -----------------------------------------------
    )
    echo.
    if not defined CONFIRM (
        choice /C YN /M "  Proceed with removing Lumiya isolated environment"
        if errorlevel 2 (
            echo   Uninstallation aborted.
            exit /b 0
        )
    )
)

echo.
echo   Removing local .env virtual environment...
if exist "%~dp0.env" (
    rd /s /q "%~dp0.env"
    echo   [%GREEN%REMOVED%RESET%] Local .env directory deleted.
)

echo   Removing Conda environment 'lumiya'...
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
    "!CONDA_EXE!" env remove -n lumiya -y >nul 2>&1
    "!CONDA_EXE!" clean --all -y >nul 2>&1
    echo   [%GREEN%REMOVED%RESET%] Conda environment 'lumiya' removed.
) else (
    where conda >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        call conda env remove -n lumiya -y >nul 2>&1
        call conda clean --all -y >nul 2>&1
        echo   [%GREEN%REMOVED%RESET%] Conda environment 'lumiya' removed.
    )
)

for %%E in (
    "%USERPROFILE%\miniconda3\envs\lumiya"
    "%USERPROFILE%\anaconda3\envs\lumiya"
    "%USERPROFILE%\.conda\envs\lumiya"
    "%LOCALAPPDATA%\miniconda3\envs\lumiya"
    "C:\miniconda3\envs\lumiya"
) do (
    if exist "%%~E" rd /s /q "%%~E" >nul 2>&1
)

for /d /r "%~dp0" %%D in (__pycache__) do @if exist "%%~D" rd /s /q "%%~D" >nul 2>&1

if "%MODE%"=="PURGE" (
    echo   Purging runtime manifest and temporary logs...
    if exist "%~dp0user\install_manifest.log" del /f /q "%~dp0user\install_manifest.log" >nul 2>&1
    if exist "%~dp0user\history.json" del /f /q "%~dp0user\history.json" >nul 2>&1
    echo.
    echo   ====================================================================================================
    echo   [%GREEN%COMPLETE%RESET%] Thorough uninstallation finished.
    echo   All runtime pillars ^(Conda 'lumiya' environment, .env, and caches^)
    echo   have been purged.
    echo.
    echo   The program folder and your exported photos ^(results\^) were kept intact
    echo   so you can manage remaining data at your discretion.
    echo   ====================================================================================================
    if not defined CONFIRM pause
    exit /b 0
)

echo.
echo   ====================================================================================================
echo   [%GREEN%CLEAN%RESET%] Uninstallation complete. Isolated environment removed.
echo   The program folder and exported photos ^(results\^) were preserved.
echo   ====================================================================================================
if not defined CONFIRM pause
