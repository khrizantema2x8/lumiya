@echo off
setlocal EnableDelayedExpansion
title PORTtralica Lumiya v0.6.021.4330 (Pilot) - Environment Installer
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
goto proceed_installer

:show_help
echo ========================================================================
echo   PORTtralica Lumiya v0.6.021.4330 (Pilot) - INSTALLER REFERENCE
echo ========================================================================
echo.
echo Usage: install.bat [OPTIONS]
echo.
echo Options:
echo   --uninstall, -u       Remove this program footprint dependencies (default: manifest cleanup)
echo   --purge, -p           Thoroughly purge runtime pillars
echo   -y, --yes             Skip interactive confirmations
echo   -h, --help, /?        Display this help reference
exit /b 0

:forward_uninstall
call "%~dp0uninstall.bat" %*
exit /b %ERRORLEVEL%

:proceed_installer

chcp 65001 >nul 2>&1
for /F %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "LOGO_GOLD=%ESC%[38;2;243;214;137m"
set "DIM=%ESC%[90m"
set "GREEN=%ESC%[92m"
set "YELLOW=%ESC%[93m"
set "RED=%ESC%[91m"
set "CYAN=%ESC%[96m"
set "RESET=%ESC%[0m"

set "USER_DIR=%~dp0user"
if not exist "%USER_DIR%" mkdir "%USER_DIR%"
set "MANIFEST=%USER_DIR%\install_manifest.log"
set "PRE_LIST=%TEMP%\lumiya_pre.txt"
set "POST_LIST=%TEMP%\lumiya_post.txt"

echo ======================================================================== > "%MANIFEST%"
echo   PORTtralica Lumiya v0.6.021.4330 (Pilot) - INSTALLATION MANIFEST >> "%MANIFEST%"
echo   Timestamp : %DATE% %TIME% >> "%MANIFEST%"
echo   Username  : %USERNAME% >> "%MANIFEST%"
echo ======================================================================== >> "%MANIFEST%"

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
echo   %DIM%PORTtralica Lumiya v0.6.021.4330 (Pilot) - SYSTEM AUDIT ^& INSTALLER%RESET%
echo   ====================================================================================================
echo.

set "MISSING_CORE=0"

:: 1. Check Git
where git >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    echo   [%GREEN%OK%RESET%]      Git CLI detected.
    echo [FOUNDATION] Git CLI: Installed >> "%MANIFEST%"
) else (
    echo   [%YELLOW%WARN%RESET%]    Git CLI not found in PATH. Install from https://git-scm.com/
    echo [FOUNDATION] Git CLI: MISSING ^(Install Git for Windows^) >> "%MANIFEST%"
)

:: 2. Locate Conda safely (even with spaces in username)
set "CONDA_ACTIVATE="
for %%P in (
    "%USERPROFILE%\miniconda3\Scripts\activate.bat"
    "%USERPROFILE%\anaconda3\Scripts\activate.bat"
    "%LOCALAPPDATA%\miniconda3\Scripts\activate.bat"
    "%LOCALAPPDATA%\anaconda3\Scripts\activate.bat"
    "%PROGRAMDATA%\miniconda3\Scripts\activate.bat"
    "%PROGRAMDATA%\anaconda3\Scripts\activate.bat"
    "C:\miniconda3\Scripts\activate.bat"
    "C:\anaconda3\Scripts\activate.bat"
) do (
    if not defined CONDA_ACTIVATE (
        if exist "%%~P" set "CONDA_ACTIVATE=%%~P"
    )
)

if not defined CONDA_ACTIVATE (
    for /f "usebackq delims=" %%C in (`where conda 2^>nul`) do (
        if not defined CONDA_ACTIVATE (
            for %%D in ("%%~dpC..\Scripts\activate.bat") do (
                if exist "%%~fD" set "CONDA_ACTIVATE=%%~fD"
            )
        )
    )
)

if defined CONDA_ACTIVATE (
    echo   [%GREEN%OK%RESET%]      Conda located at: "!CONDA_ACTIVATE!"
    echo [FOUNDATION] Conda: "!CONDA_ACTIVATE!" >> "%MANIFEST%"
) else (
    echo   [%RED%MISSING%RESET%] Miniconda3 / Anaconda3 not found.
    echo [FOUNDATION] Conda: MISSING >> "%MANIFEST%"
    set "MISSING_CORE=1"
)

:: 3. Detect GPU Hardware to select appropriate PyTorch build
set "HAS_NVIDIA=0"
set "GPU_MODEL=CPU Only ^(No NVIDIA GPU Detected^)"
nvidia-smi --query-gpu=name --format=csv,noheader > "%TEMP%\lumiya_gpu.txt" 2>nul
if !ERRORLEVEL! EQU 0 (
    for /f "usebackq delims=" %%G in ("%TEMP%\lumiya_gpu.txt") do (
        set "HAS_NVIDIA=1"
        set "GPU_MODEL=%%G"
    )
)
if exist "%TEMP%\lumiya_gpu.txt" del /f /q "%TEMP%\lumiya_gpu.txt"

echo   [%CYAN%SYSTEM%RESET%]  Hardware Target: !GPU_MODEL!
echo [HARDWARE] Detected Target: !GPU_MODEL! >> "%MANIFEST%"

if "!MISSING_CORE!"=="1" (
    echo.
    echo   ====================================================================================================
    echo   %RED%[INSTALLATION HALTED // MISSING REQUIRED FOUNDATIONS]%RESET%
    echo   Please install the following before running install.bat again:
    echo     1. Miniconda3 ^(64-bit^) : https://docs.conda.io/en/latest/miniconda.html
    echo     2. Git for Windows     : https://git-scm.com/download/win
    echo.
    echo   %YELLOW%[NOTE]%RESET% Remember to tick "Add Conda to PATH" during Miniconda setup!
    echo   ====================================================================================================
    echo.
    echo   Press any key to exit...
    pause >nul
    exit /b 1
)

call "!CONDA_ACTIVATE!"

:: 4. Auto-accept Anaconda Terms of Service without mutating user's global .condarc always_yes
echo.
echo   [01/05] Accepting Conda channel terms ^& preparing isolated install...
call conda tos accept >nul 2>&1
call conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main >nul 2>&1
call conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r >nul 2>&1
call conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/msys2 >nul 2>&1

:: 5. Determine or Create Environment (lumiya)
set "ENV_NAME=lumiya"

call conda info --envs | findstr /I "\b!ENV_NAME!\b" >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo   [02/05] Creating isolated Python 3.13 environment '!ENV_NAME!'...
    call conda create -n !ENV_NAME! python=3.13 -c conda-forge --override-channels -y
    if !ERRORLEVEL! NEQ 0 (
        call conda create -n !ENV_NAME! python=3.13 -y
    )
    echo [ENV] Created environment: !ENV_NAME! ^(Python 3.13^) >> "%MANIFEST%"
) else (
    echo   [02/05] Using existing environment '!ENV_NAME!'...
    echo [ENV] Kept existing environment: !ENV_NAME! >> "%MANIFEST%"
)

call "!CONDA_ACTIVATE!" !ENV_NAME!
if !ERRORLEVEL! NEQ 0 (
    echo   [%RED%ERROR%RESET%] Failed to activate '!ENV_NAME!'.
    echo   Press any key to exit...
    pause >nul
    exit /b 1
)

python -m pip list --format=freeze > "%PRE_LIST%"

echo   [03/05] Installing hardware-matched PyTorch for [!GPU_MODEL!]...
:: The driver sets the newest CUDA build it can run: try builds newest first, then fall back to CPU.
set "CUDA_NUM=0"
if "!HAS_NVIDIA!"=="1" (
    for /f "tokens=3 delims=:" %%A in ('nvidia-smi ^| findstr /C:"CUDA Version"') do (
        for /f "tokens=1,2 delims=. " %%B in ("%%A") do set /a "CUDA_NUM=%%B*10+%%C"
    )
)
echo   [%CYAN%SYSTEM%RESET%]  Driver CUDA level: !CUDA_NUM!
set "TORCH_BUILD="
for %%C in (132 130 128 126 124 121 118) do (
    if not defined TORCH_BUILD if !CUDA_NUM! GEQ %%C (
        echo   [03/05] Trying PyTorch CUDA wheel cu%%C...
        python -m pip install --force-reinstall --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu%%C
        if !ERRORLEVEL! EQU 0 (
            python -c "import torch; raise SystemExit(0 if torch.cuda.is_available() else 1)" >nul 2>&1
            if !ERRORLEVEL! EQU 0 (
                set "TORCH_BUILD=cu%%C"
                echo   [%GREEN%VERIFIED%RESET%] PyTorch cu%%C initialized CUDA successfully.
            ) else (
                echo   [%YELLOW%FALLBACK%RESET%] PyTorch cu%%C installed but driver rejected runtime; stepping down...
            )
        )
    )
)
if not defined TORCH_BUILD (
    python -m pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu && set "TORCH_BUILD=cpu"
)
echo [HARDWARE] Torch build: !TORCH_BUILD! >> "%MANIFEST%"

echo   [04/05] Installing pinned diffusion, image ^& telemetry packages...
if not "!TORCH_BUILD!"=="cpu" if defined TORCH_BUILD (
    python -m pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/!TORCH_BUILD! "diffusers>=0.30.0" "transformers>=4.44.0" "accelerate>=0.33.0" "huggingface-hub>=0.24.0" "safetensors>=0.4.3" "Pillow>=10.3.0" "psutil>=5.9.8" "numpy>=1.26.0" "nvidia-ml-py>=12.535.133"
) else (
    python -m pip install --no-cache-dir "diffusers>=0.30.0" "transformers>=4.44.0" "accelerate>=0.33.0" "huggingface-hub>=0.24.0" "safetensors>=0.4.3" "Pillow>=10.3.0" "psutil>=5.9.8" "numpy>=1.26.0" "nvidia-ml-py>=12.535.133"
)

python -m pip list --format=freeze > "%POST_LIST%"

echo. >> "%MANIFEST%"
echo --- [1] TARGET SPECIFICATION --- >> "%MANIFEST%"
echo Python=3.13, torch (driver-matched build), torchvision, diffusers, transformers, accelerate, Pillow>=10.3.0, psutil>=5.9.8 >> "%MANIFEST%"

echo. >> "%MANIFEST%"
echo --- [2] KEPT PACKAGES --- >> "%MANIFEST%"
for /f "usebackq delims=" %%P in ("%PRE_LIST%") do (
    echo   [KEPT] %%P >> "%MANIFEST%"
)

echo. >> "%MANIFEST%"
echo --- [3] NEWLY INSTALLED PACKAGES --- >> "%MANIFEST%"
set "ADDED=0"
for /f "usebackq delims=" %%A in ("%POST_LIST%") do (
    findstr /X /C:"%%A" "%PRE_LIST%" >nul 2>&1
    if !ERRORLEVEL! NEQ 0 (
        echo   [NEW]  %%A >> "%MANIFEST%"
        set /a ADDED+=1
    )
)
if "!ADDED!"=="0" echo   (All target packages were already installed) >> "%MANIFEST%"

echo. >> "%MANIFEST%"
echo --- [4] VERIFICATION MATRIX --- >> "%MANIFEST%"
for %%M in (torch torchvision diffusers transformers accelerate PIL psutil) do (
    python -c "import %%M; print('  [VERIFIED] %%M ->', getattr(%%M, '__version__', 'OK'))" >> "%MANIFEST%" 2>nul || (
        echo   [MISSING]  %%M >> "%MANIFEST%"
    )
)

echo   [05/05] Purging installer caches ^& temporary files...
if exist "%PRE_LIST%" del /f /q "%PRE_LIST%"
if exist "%POST_LIST%" del /f /q "%POST_LIST%"
python -m pip cache purge >nul 2>&1
call conda clean --all -y >nul 2>&1
for /d /r "%~dp0" %%D in (__pycache__) do @if exist "%%~D" rd /s /q "%%~D"

echo.
echo   ====================================================================================================
echo   [%GREEN%COMPLETE%RESET%] Environment '!ENV_NAME!' is ready. Manifest saved to:
echo              user\install_manifest.log
echo   ====================================================================================================
echo.
echo   Press any key to close installer...
pause >nul
exit /b 0

