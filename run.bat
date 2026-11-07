@echo off
setlocal EnableDelayedExpansion
title PORTtralica Lumiya v0.6.021.4330 (Pilot)
cd /d "%~dp0"

if /I "%~1"=="-h" goto show_help
if /I "%~1"=="--help" goto show_help
if /I "%~1"=="/h" goto show_help
if /I "%~1"=="/?" goto show_help
if /I "%~1"=="/uninstall" goto forward_uninstall
if /I "%~1"=="--uninstall" goto forward_uninstall
if /I "%~1"=="-u" goto forward_uninstall
if /I "%~1"=="/purge" goto forward_uninstall
if /I "%~1"=="--purge" goto forward_uninstall
if /I "%~1"=="-p" goto forward_uninstall
if /I "%~1"=="purge" goto forward_uninstall
if /I "%~1"=="free-port" goto do_free_port
if /I "%~1"=="--free-port" goto do_free_port
if /I "%~1"=="kill-port" goto do_free_port
if /I "%~1"=="--kill-port" goto do_free_port
goto proceed_run

:show_help
echo ========================================================================
echo   PORTtralica Lumiya v0.6.021.4330 (Pilot) - CLI REFERENCE
echo ========================================================================
echo.
echo Usage: run.bat [SUBCOMMAND ^| OPTIONS]
echo.
echo Subcommands:
echo   install               Provision environment ^& install dependencies
echo   uninstall             Remove this program footprint dependencies (default: manifest cleanup)
echo   purge                 Thoroughly purge runtime pillars
echo   free-port [port]      Kill process occupying port (default: 7860)
echo.
echo Options:
echo   --uninstall, -u       Remove this program footprint dependencies (default: manifest cleanup)
echo   --purge, -p           Thoroughly purge runtime pillars
echo   -y, --yes             Skip interactive confirmations
echo   -h, --help, /?        Display this help reference
echo.
echo All other arguments (e.g. --port 7860, --debug, --no-browser) are forwarded to protect.py.
exit /b 0

:forward_uninstall
call "%~dp0uninstall.bat" %*
exit /b %ERRORLEVEL%

:do_free_port
set "FREE_PORT=%~2"
if "%FREE_PORT%"=="" set "FREE_PORT=7860"
echo   [PORT] Freeing port %FREE_PORT% and terminating lingering processes...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :%FREE_PORT%') do taskkill /f /pid %%a >nul 2>&1
echo   [CLEARED] Port %FREE_PORT% cleared.
exit /b 0

:proceed_run

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
echo   %DIM%PORTtralica Lumiya - v0.6.021.4330 (Pilot) - (c) 2026 PORTtralica Media Group%RESET%
echo   ====================================================================================================
echo.

:: 1. Check Git
where git >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    echo   [%GREEN%FOUND%RESET%]     Git CLI                : Installed in PATH
) else (
    if exist "%ProgramFiles%\Git\cmd\git.exe" (
        set "PATH=%ProgramFiles%\Git\cmd;%PATH%"
        echo   [%GREEN%FOUND%RESET%]     Git CLI                : %ProgramFiles%\Git\cmd\git.exe
    ) else (
        echo   [%YELLOW%MISSING%RESET%]   Git CLI                : Not detected ^(Recommended: Git 2.45+^)
    )
)

:: 2. Check self-contained local .env inside the project folder first (folder-name independent)
set "SELECTED_ENV="
set "SELECTED_PY="
set "FALLBACK_ENV="
set "FALLBACK_PY="

if exist "%~dp0.env\python.exe" (
    "%~dp0.env\python.exe" -c "import importlib.util as u; raise SystemExit(0 if (u.find_spec('torch') and u.find_spec('diffusers') and u.find_spec('PIL')) else 1)" >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        set "SELECTED_ENV=.env (Local Self-Contained)"
        set "SELECTED_PY=%~dp0.env\python.exe"
    ) else (
        set "FALLBACK_ENV=.env (Local Self-Contained)"
        set "FALLBACK_PY=%~dp0.env\python.exe"
    )
)

:: 3. Locate Conda Root Directory across all standard paths
set "CONDA_ROOT="
for %%R in (
    "%USERPROFILE%\miniconda3"
    "%USERPROFILE%\anaconda3"
    "%LOCALAPPDATA%\miniconda3"
    "%LOCALAPPDATA%\anaconda3"
    "%PROGRAMDATA%\miniconda3"
    "%PROGRAMDATA%\anaconda3"
    "C:\miniconda3"
    "C:\anaconda3"
) do (
    if not defined CONDA_ROOT (
        if exist "%%~R\Scripts\activate.bat" set "CONDA_ROOT=%%~R"
    )
)

if not defined CONDA_ROOT (
    for /f "usebackq delims=" %%C in (`where conda 2^>nul`) do (
        if not defined CONDA_ROOT (
            for %%D in ("%%~dpC..") do (
                if exist "%%~fD\Scripts\activate.bat" set "CONDA_ROOT=%%~fD"
            )
        )
    )
)

if defined CONDA_ROOT (
    echo   [%GREEN%FOUND%RESET%]     Conda Root             : "!CONDA_ROOT!"
) else if not defined SELECTED_PY (
    echo   [%RED%MISSING%RESET%]   Conda Manager          : Miniconda3 / Anaconda3 not found
    echo.
    echo   ====================================================================================================
    echo   %RED%[PRE-FLIGHT MANIFEST // MISSING FOUNDATIONS]%RESET%
    echo     1. Miniconda3 ^(Python 3.13+^) : https://docs.conda.io/en/latest/miniconda.html
    echo     2. Git for Windows           : https://git-scm.com/download/win
    echo   %YELLOW%[IMPORTANT]%RESET% Tick "Add Miniconda3 to my PATH environment variable" during installation.
    echo   ====================================================================================================
    echo.
    echo   Press any key to exit...
    pause >nul
    exit /b 1
)

:: 4. Probe Conda environment (lumiya, or any env with torch+diffusers+PIL)
if not defined SELECTED_PY if defined CONDA_ROOT (
    for %%E in (lumiya) do (
        set "CAND_PY=!CONDA_ROOT!\envs\%%E\python.exe"
        if exist "!CAND_PY!" (
            if not defined FALLBACK_PY (
                set "FALLBACK_ENV=%%E"
                set "FALLBACK_PY=!CAND_PY!"
            )
            if not defined SELECTED_PY (
                "!CAND_PY!" -c "import importlib.util as u; raise SystemExit(0 if (u.find_spec('torch') and u.find_spec('diffusers') and u.find_spec('PIL')) else 1)" >nul 2>&1
                if !ERRORLEVEL! EQU 0 (
                    set "SELECTED_ENV=%%E"
                    set "SELECTED_PY=!CAND_PY!"
                )
            )
        )
    )
)

if not defined SELECTED_PY if defined CONDA_ROOT (
    for /d %%D in ("!CONDA_ROOT!\envs\*") do (
        if not defined SELECTED_PY if exist "%%~fD\python.exe" (
            "%%~fD\python.exe" -c "import importlib.util as u; raise SystemExit(0 if (u.find_spec('torch') and u.find_spec('diffusers') and u.find_spec('PIL')) else 1)" >nul 2>&1
            if !ERRORLEVEL! EQU 0 (
                set "SELECTED_ENV=%%~nxD"
                set "SELECTED_PY=%%~fD\python.exe"
            )
        )
    )
)

if not defined SELECTED_PY if defined CONDA_ROOT (
    if exist "!CONDA_ROOT!\python.exe" (
        "!CONDA_ROOT!\python.exe" -c "import importlib.util as u; raise SystemExit(0 if (u.find_spec('torch') and u.find_spec('diffusers') and u.find_spec('PIL')) else 1)" >nul 2>&1
        if !ERRORLEVEL! EQU 0 (
            set "SELECTED_ENV=base"
            set "SELECTED_PY=!CONDA_ROOT!\python.exe"
        )
    )
)

if not defined SELECTED_PY (
    if defined FALLBACK_PY (
        set "SELECTED_ENV=!FALLBACK_ENV!"
        set "SELECTED_PY=!FALLBACK_PY!"
    )
)

if not defined SELECTED_PY (
    echo   [%YELLOW%MISSING%RESET%]   Python Environment     : No initialized environment found
    echo.
    echo   ====================================================================================================
    echo   %YELLOW%[ENVIRONMENT NOT INITIALIZED]%RESET%
    echo     [I] Run 'install.bat' now to create environment ^& install packages
    echo     [W] Launch WebUI in limited mode ^(using base Python^)
    echo     [Q] Exit
    echo   ====================================================================================================
    choice /C IWQ /N /M "  Select option [I / W / Q]: "
    set "CHOICE_RES=!ERRORLEVEL!"
    if "!CHOICE_RES!"=="1" (
        call "%~dp0install.bat"
        choice /C NL /N /M "  Installation finished. Reboot [N]ow or [L]ater? "
        if "!ERRORLEVEL!"=="1" (
            shutdown /r /t 5
            exit /b 0
        )
        echo   %YELLOW%Without a reboot the program will be unreliable and may not work as intended.%RESET%
        if exist "%~dp0.env\python.exe" (
            set "SELECTED_ENV=.env"
            set "SELECTED_PY=%~dp0.env\python.exe"
        ) else if exist "!CONDA_ROOT!\envs\lumiya\python.exe" (
            set "SELECTED_ENV=lumiya"
            set "SELECTED_PY=!CONDA_ROOT!\envs\lumiya\python.exe"
        )
    ) else if "!CHOICE_RES!"=="2" (
        set "SELECTED_ENV=base"
        set "SELECTED_PY=!CONDA_ROOT!\python.exe"
    ) else (
        exit /b 0
    )
)

if defined CONDA_ROOT (
    call "!CONDA_ROOT!\Scripts\activate.bat" !SELECTED_ENV! >nul 2>&1
)
set "HW_INFO=CPU Only (No NVIDIA GPU detected)"
nvidia-smi --query-gpu=name --format=csv,noheader > "%TEMP%\lumiya_gpu_run.txt" 2>nul
if !ERRORLEVEL! EQU 0 (
    set /p "DETECTED_GPU=" < "%TEMP%\lumiya_gpu_run.txt"
    for /f "tokens=3 delims=:" %%A in ('nvidia-smi 2^>nul ^| findstr /C:"CUDA Version"') do (
        for /f "tokens=1,2 delims=. " %%B in ("%%A") do (
            set "HW_INFO=!DETECTED_GPU! (CUDA %%B.%%C)"
        )
    )
)
if exist "%TEMP%\lumiya_gpu_run.txt" del /f /q "%TEMP%\lumiya_gpu_run.txt"
echo   [%CYAN%TARGET%RESET%]    Hardware / CUDA        : !HW_INFO!
echo   [%GREEN%ACTIVE%RESET%]    Environment            : !SELECTED_ENV! ^("!SELECTED_PY!"^)
echo   ====================================================================================================
echo.

"!SELECTED_PY!" "%~dp0protect.py" %*
echo.
echo   [SERVICE STOPPED] Press any key to close this window...
pause >nul
