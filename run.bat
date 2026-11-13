@echo off
setlocal EnableDelayedExpansion
rem Version is written once, in core\config.py.
for /f tokens^=2^ delims^=^" %%v in ('findstr /b /c:"APP_VERSION = " "%~dp0core\config.py"') do set "LMY_VER=%%v"
if not defined LMY_VER set "LMY_VER=unknown version"
title PORTtralica Lumiya !LMY_VER!
cd /d "%~dp0"

if /I "%~1"=="-h" goto show_help
if /I "%~1"=="--help" goto show_help
if /I "%~1"=="/h" goto show_help
if /I "%~1"=="/?" goto show_help
if /I "%~1"=="install" (
    shift
    call "%~dp0install.bat" %*
    exit /b %ERRORLEVEL%
)
if /I "%~1"=="--install" (
    shift
    call "%~dp0install.bat" %*
    exit /b %ERRORLEVEL%
)
if /I "%~1"=="-i" (
    shift
    call "%~dp0install.bat" %*
    exit /b %ERRORLEVEL%
)
if /I "%~1"=="setup" (
    shift
    call "%~dp0install.bat" %*
    exit /b %ERRORLEVEL%
)
if /I "%~1"=="/uninstall" goto forward_uninstall
if /I "%~1"=="--uninstall" goto forward_uninstall
if /I "%~1"=="-u" goto forward_uninstall
if /I "%~1"=="uninstall" goto forward_uninstall
if /I "%~1"=="remove" goto forward_uninstall
if /I "%~1"=="/purge" goto forward_uninstall
if /I "%~1"=="--purge" goto forward_uninstall
if /I "%~1"=="purge" goto forward_uninstall
if /I "%~1"=="free-port" goto do_free_port
if /I "%~1"=="--free-port" goto do_free_port
if /I "%~1"=="kill-port" goto do_free_port
if /I "%~1"=="--kill-port" goto do_free_port
if /I "%~1"=="reinstall-torch" goto do_reinstall_torch
if /I "%~1"=="fix-cuda" goto do_reinstall_torch
if /I "%~1"=="--reinstall-torch" goto do_reinstall_torch
if /I "%~1"=="clean" (
    shift
    set "EXTRA_DOCTOR=--clean"
    goto proceed_run
)
if /I "%~1"=="--clean" (
    shift
    set "EXTRA_DOCTOR=--clean"
    goto proceed_run
)
if /I "%~1"=="integrity" (
    shift
    set "EXTRA_DOCTOR=--integrity"
    goto proceed_run
)
if /I "%~1"=="--integrity" (
    shift
    set "EXTRA_DOCTOR=--integrity"
    goto proceed_run
)
if /I "%~1"=="cluster" (
    shift
    set "EXTRA_DOCTOR=--cluster"
    goto proceed_run
)
if /I "%~1"=="doctor" (
    shift
    set "EXTRA_DOCTOR=--doctor"
    goto proceed_run
)
if /I "%~1"=="update" (
    shift
    set "EXTRA_DOCTOR=--update"
    goto proceed_run
)
if /I "%~1"=="--update" (
    shift
    set "EXTRA_DOCTOR=--update"
    goto proceed_run
)
if /I "%~1"=="headless" (
    shift
    set "EXTRA_DOCTOR=--headless"
    goto proceed_run
)
if /I "%~1"=="-p" goto handle_port_flag
if /I "%~1"=="--port" goto handle_port_flag
if /I "%~1"=="port" goto handle_port_flag
goto check_numeric_port

:handle_port_flag
set "CLI_PORT=%~2"
shift
shift
goto proceed_run

:check_numeric_port
echo %~1| findstr /r "^[0-9][0-9]*$" >nul 2>&1
if not errorlevel 1 (
    set "CLI_PORT=%~1"
    shift
)
goto proceed_run

:show_help
chcp 65001 >nul 2>&1
for /F %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "LOGO_GOLD=%ESC%[38;2;243;214;137m"
set "DIM=%ESC%[90m"
set "RESET=%ESC%[0m"
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
echo   %DIM%PORTtralica Lumiya - !LMY_VER! - CLI REFERENCE%RESET%
echo   ====================================================================================================
echo.
echo Usage: run.bat [SUBCOMMAND ^| OPTIONS]
echo.
echo Subcommands:
echo   install, setup        Provision environment ^& install dependencies
echo   update                Protected GitHub self-pull ^& dependency/integrity check
echo   integrity, verify     Verify SHA-256 and MD5 checksums against core/integrity.lmy
echo   reinstall-torch [cu]  Reinstall CUDA PyTorch into active environment (auto-detects driver CUDA)
echo   uninstall, remove     Remove this program footprint dependencies (default: manifest cleanup)
echo   purge                 Thoroughly purge runtime pillars
echo   free-port [port]      Kill process occupying port (default: 7860)
echo   clean                 Purge cache and temporary workspace files
echo   doctor                Run hardware, CUDA, NVML, font, and storage diagnostics
echo   cluster               Launch in shared cluster/HPC mode (--no-browser, smart TMPDIR)
echo   headless              Run batch protection directly from CLI without WebUI
echo.
echo Options:
echo   -p, --port [port]     Bind WebUI to specific port (e.g. -p 7860 or run.bat 7860)
echo   --host [host]         Bind to interface (default: 127.0.0.1, use 0.0.0.0 for LAN/remote)
echo   --listen              Bind to 0.0.0.0 (allow remote or LAN access)
echo   --auth-token [token]  Require access token for WebUI API requests
echo   --no-browser          Do not automatically launch system browser
echo   --tmp-dir [dir]       Override temporary directory
echo   --cache-dir [dir]     Override PyTorch/HuggingFace/pip cache directory
echo   --results-dir [dir]   Override exported results directory
echo   --device [dev]        Force compute backend (auto, cuda, cpu)
echo   --gpu [id]            Select GPU index (sets CUDA_VISIBLE_DEVICES)
echo   --tile-size [px]      Override spatial PGD tile size (256-1024)
echo   --low-vram            Enable low-VRAM optimizations (512px tiles, fp16, RAM spillover)
echo   --headless -i [path]  Run CLI batch immunization on file/folder (with -o, --algo, --steps, --budget)
echo   --debug               Launch backend in emulation / verbose mode
echo   --uninstall, -u       Remove this program footprint dependencies (default: manifest cleanup)
echo   --purge               Thoroughly purge runtime pillars
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

:do_reinstall_torch
set "TARGET_WHEEL=%~2"
if exist "%USERPROFILE%\miniconda3\Scripts\activate.bat" (
    call "%USERPROFILE%\miniconda3\Scripts\activate.bat" lumiya >nul 2>&1
) else if exist "C:\ProgramData\miniconda3\Scripts\activate.bat" (
    call "C:\ProgramData\miniconda3\Scripts\activate.bat" lumiya >nul 2>&1
)
if "%TARGET_WHEEL%"=="" (
    set "CUDA_NUM=0"
    for /f "tokens=3 delims=:" %%A in ('nvidia-smi 2^>nul ^| findstr /C:"CUDA Version"') do (
        for /f "tokens=1,2 delims=. " %%B in ("%%A") do set /a "CUDA_NUM=%%B*10+%%C"
    )
    for %%C in (132 130 128 126 124 121 118) do (
        if not defined TARGET_WHEEL if !CUDA_NUM! GEQ %%C (
            echo   [CUDA] Querying https://download.pytorch.org/whl/cu%%C for PyTorch CUDA wheel cu%%C...
            python -m pip install --upgrade --force-reinstall --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu%%C
            if !ERRORLEVEL! EQU 0 set "TARGET_WHEEL=cu%%C"
        )
    )
    if not defined TARGET_WHEEL (
        set "TARGET_WHEEL=cpu"
        python -m pip install --upgrade --force-reinstall --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
    )
) else if "!TARGET_WHEEL!"=="cpu" (
    echo   [CUDA] Reinstalling PyTorch (!TARGET_WHEEL!) into active environment...
    python -m pip install --upgrade --force-reinstall --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
) else (
    echo   [CUDA] Reinstalling PyTorch (!TARGET_WHEEL!) into active environment...
    python -m pip install --upgrade --force-reinstall --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/!TARGET_WHEEL!
)
python -c "import torch; print('  [VERIFIED] CUDA Available:', torch.cuda.is_available(), '| Build:', getattr(torch.version, 'cuda', None))"
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
echo   %DIM%PORTtralica Lumiya - !LMY_VER! - (c) 2026 PORTtralica Media Group%RESET%
echo   ====================================================================================================

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
if not exist "%~dp0.git" (
    where git >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        git init -q >nul 2>&1
        git remote add origin https://github.com/khrizantema2x8/lumiya.git >nul 2>&1
        git fetch --quiet --depth=20 origin main >nul 2>&1
        if !ERRORLEVEL! EQU 0 (
            git branch -M main >nul 2>&1
            git reset --mixed origin/main >nul 2>&1
            echo   [%GREEN%ATTACHED%RESET%]  Git Repository         : Auto-linked to official GitHub origin
        ) else (
            if exist "%~dp0.git" rd /s /q "%~dp0.git" >nul 2>&1
        )
    )
)

:: 2. Remove any legacy local .env virtualenv so Lumiya strictly uses Conda
set "SELECTED_ENV="
set "SELECTED_PY="
set "FALLBACK_ENV="
set "FALLBACK_PY="
if exist "%~dp0.env" rd /s /q "%~dp0.env" >nul 2>&1

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

:: 4. Probe Conda environment (lumiya) with verbose diagnostic feedback
set "ERRLOG=%~dp0user\error.log"
if not exist "%~dp0user" mkdir "%~dp0user" >nul 2>&1
if not defined SELECTED_PY if defined CONDA_ROOT (
    for %%E in (lumiya) do (
        set "CAND_PY=!CONDA_ROOT!\envs\%%E\python.exe"
        if exist "!CAND_PY!" (
            echo   [%CYAN%PROBE%RESET%]     Inspecting Conda Env   : "!CAND_PY!"
            if not defined FALLBACK_PY (
                set "FALLBACK_ENV=%%E"
                set "FALLBACK_PY=!CAND_PY!"
            )
            if not defined SELECTED_PY (
                "!CAND_PY!" -c "import importlib.util as u; missing=[m for m in ('torch','diffusers','PIL','psutil') if not u.find_spec(m)]; print('  [DIAG]      Missing packages       :', ', '.join(missing)) if missing else None; raise SystemExit(0 if not missing else 1)"
                if !ERRORLEVEL! EQU 0 (
                    set "SELECTED_ENV=%%E"
                    set "SELECTED_PY=!CAND_PY!"
                ) else (
                    echo [%DATE% %TIME%] [run.bat] Environment '!CAND_PY!' missing core packages. >> "!ERRLOG!"
                )
            )
        ) else (
            echo   [%DIM%PROBE%RESET%]     Conda Env Path         : "!CAND_PY!" ^(not created yet^)
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
        set "LUMIYA_CALLER=1"
        call "%~dp0install.bat"
        set "LUMIYA_CALLER="
        choice /C NL /N /M "  Installation finished. Reboot [N]ow or [L]ater? "
        if "!ERRORLEVEL!"=="1" (
            shutdown /r /t 5
            exit /b 0
        )
        echo   %YELLOW%Without a reboot the program will be unreliable and may not work as intended.%RESET%
        if exist "!CONDA_ROOT!\envs\lumiya\python.exe" (
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
set "HW_INFO=CPU Only ^(No NVIDIA GPU detected^)"
nvidia-smi --query-gpu=name --format=csv,noheader > "%TEMP%\lumiya_gpu_run.txt" 2>nul
if !ERRORLEVEL! EQU 0 (
    set /p "DETECTED_GPU=" < "%TEMP%\lumiya_gpu_run.txt"
    for /f "tokens=3 delims=:" %%A in ('nvidia-smi 2^>nul ^| findstr /C:"CUDA Version"') do (
        for /f "tokens=1,2 delims=. " %%B in ("%%A") do (
            set "HW_INFO=!DETECTED_GPU! ^(CUDA %%B.%%C^)"
        )
    )
)
if exist "%TEMP%\lumiya_gpu_run.txt" del /f /q "%TEMP%\lumiya_gpu_run.txt"
echo   [%CYAN%TARGET%RESET%]    Hardware / CUDA        : !HW_INFO!
echo   [%GREEN%ACTIVE%RESET%]    Environment            : !SELECTED_ENV! ^("!SELECTED_PY!"^)
"!SELECTED_PY!" -c "import sys, torch; print(f'  [\x1b[96mRUNTIME\x1b[0m]   PyTorch / Python       : torch {torch.__version__} (CUDA={torch.cuda.is_available()}, build={getattr(torch.version, \"cuda\", None)}) // Python {sys.version.split()[0]}')" 2>nul
echo   [%DIM%LOGFILE%RESET%]   Diagnostic Error Log   : "%~dp0user\error.log"
echo   ====================================================================================================

set "LUMIYA_BANNER_PRINTED=1"
set "PORT_ARG="
if defined CLI_PORT set "PORT_ARG=--port !CLI_PORT!"

"!SELECTED_PY!" "%~dp0protect.py" !PORT_ARG! !EXTRA_DOCTOR! %*
set "EXIT_CODE=!ERRORLEVEL!"
if !EXIT_CODE! NEQ 0 (
    echo [%DATE% %TIME%] [run.bat] protect.py exited with non-zero code !EXIT_CODE!. >> "!ERRLOG!"
    echo   [%RED%ERROR%RESET%]     Service exited with code !EXIT_CODE!. Diagnostic details written to user\error.log
)
echo.
echo   [SERVICE STOPPED] Press any key to close this window...
pause >nul
