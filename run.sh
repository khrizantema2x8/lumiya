#!/usr/bin/env bash
# ==============================================================================
# PORTtralica Lumiya v0.6.017.4110 (Pilot) - All-in-One Linux Launcher & Setup
# ==============================================================================
set -e
cd "$(dirname "$0")"

LOGO_GOLD="\033[38;2;243;214;137m"
DIM="\033[90m"
GREEN="\033[92m"
YELLOW="\033[93m"
RED="\033[91m"
CYAN="\033[96m"
RESET="\033[0m"

USER_DIR="$(pwd)/user"
mkdir -p "$USER_DIR"
MANIFEST="$USER_DIR/install_manifest.log"

print_banner() {
    echo -e "${LOGO_GOLD}"
    echo "              :::::::::::::                                                                         "
    echo "              :   :::::::::                                                                         "
    echo "                :::                                            :::                                  "
    echo "               ::                                              :::                                  "
    echo "              ::   :::       ::    ::  ::::::   ::::::       ::       ::::    :::      ::::::::     "
    echo "            :::   ::       :::     :::::   :: :::   ::     :::      :::      ::::   ::::      : :   "
    echo "           ::    ::       ::     ::::      :::     ::     :::      ::       ::::  :::        ::::   "
    echo "         :::    ::      :::    :::        ::      ::     ::      :::       :::   ::        :::    ::"
    echo ":::::   ::     ::    :::::   :::        :::     ::    ::::    :::::      :::  :::::     ::::    ::: "
    echo ":    :::       ::::::  ::::::::        ::       ::::::  :::::::  :::::::::::::   :::::::::::::::    "
    echo " ::::::::       ::                                                     ::::                         "
    echo "        :::::   ::                                                 ::::::                           "
    echo "            :::::                                                :::::::                            "
    echo "                                                              :::: :::                              "
    echo "                                                             ::: ::::                               "
    echo "                                                             ::::::                                 "
    echo -e "${RESET}"
    echo -e "  ${DIM}PORTtralica Lumiya - v0.6.017.4110 (Pilot) - (c) 2026 PORTtralica Media Group${RESET}"
    echo "  ===================================================================================================="
    echo ""
}

find_conda() {
    if command -v conda >/dev/null 2>&1; then
        which conda
        return
    fi
    for c in "$HOME/miniconda3/bin/conda" "$HOME/anaconda3/bin/conda" "$HOME/miniforge3/bin/conda" "/opt/conda/bin/conda" "/opt/miniconda3/bin/conda"; do
        if [ -x "$c" ]; then
            echo "$c"
            return
        fi
    done
}

check_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        case "$ID" in
            debian|ubuntu|linuxmint|pop)
                echo -e "  [${GREEN}VERIFIED${RESET}] OS Distribution        : ${PRETTY_NAME:-$ID} (Debian/Ubuntu family)"
                ;;
            *)
                if echo "${ID_LIKE:-}" | grep -qE "debian|ubuntu"; then
                    echo -e "  [${GREEN}VERIFIED${RESET}] OS Distribution        : ${PRETTY_NAME:-$ID} (Debian derivative)"
                else
                    echo -e "  [${YELLOW}CAUTION${RESET}]  OS Distribution        : ${PRETTY_NAME:-$ID}"
                    echo -e "  ${YELLOW}Notice: Lumiya is strictly validated for Debian/Ubuntu (64-bit).${RESET}"
                    echo -e "  ${YELLOW}Arch, openSUSE, Fedora, and other distributions are unvalidated and unsupported.${RESET}"
                fi
                ;;
        esac
    fi
}

select_env_python() {
    SELECTED_PY=""
    SELECTED_ENV=""

    # 1. Check local .env
    if [ -x "./.env/bin/python" ]; then
        if ./.env/bin/python -c "import importlib.util as u; raise SystemExit(0 if (u.find_spec('torch') and u.find_spec('diffusers') and u.find_spec('PIL')) else 1)" >/dev/null 2>&1; then
            SELECTED_PY="./.env/bin/python"
            SELECTED_ENV=".env (Local Virtual Environment)"
            return
        fi
    fi

    # 2. Check Conda 'lumiya' env
    CONDA_BIN="$(find_conda || true)"
    if [ -n "$CONDA_BIN" ]; then
        CONDA_ROOT="$("$CONDA_BIN" info --base 2>/dev/null || true)"
        if [ -n "$CONDA_ROOT" ] && [ -x "$CONDA_ROOT/envs/lumiya/bin/python" ]; then
            if "$CONDA_ROOT/envs/lumiya/bin/python" -c "import importlib.util as u; raise SystemExit(0 if (u.find_spec('torch') and u.find_spec('diffusers') and u.find_spec('PIL')) else 1)" >/dev/null 2>&1; then
                SELECTED_PY="$CONDA_ROOT/envs/lumiya/bin/python"
                SELECTED_ENV="lumiya ($CONDA_ROOT/envs/lumiya)"
                return
            fi
        fi
    fi

    # 3. Fallback to system python3
    if command -v python3 >/dev/null 2>&1; then
        SELECTED_PY="$(which python3)"
        SELECTED_ENV="system (python3)"
    fi
}

do_install() {
    print_banner
    echo -e "  [${CYAN}INSTALL${RESET}] Initializing environment setup and dependency verification..."
    PRE_LIST="$(mktemp /tmp/lumiya_pre.XXXXXX.txt)"
    POST_LIST="$(mktemp /tmp/lumiya_post.XXXXXX.txt)"
    trap 'rm -f "$PRE_LIST" "$POST_LIST"' EXIT

    echo "========================================================================" > "$MANIFEST"
    echo "  PORTtralica Lumiya v0.6.017.4110 (Pilot) - INSTALLATION MANIFEST" >> "$MANIFEST"
    echo "  Timestamp : $(date '+%Y-%m-%d %H:%M:%S')" >> "$MANIFEST"
    echo "  Username  : $(whoami 2>/dev/null || echo "$USER")" >> "$MANIFEST"
    echo "========================================================================" >> "$MANIFEST"

    # Foundation Checks
    check_distro
    if command -v git >/dev/null 2>&1; then
        echo -e "  [${GREEN}FOUND${RESET}]   Git CLI      : $(which git)"
        echo "[FOUNDATION] Git CLI: Installed ($(git --version 2>/dev/null || true))" >> "$MANIFEST"
    else
        echo -e "  [${RED}MISSING${RESET}] Git CLI      : Not found"
        echo "[FOUNDATION] Git CLI: MISSING" >> "$MANIFEST"
    fi

    CONDA_BIN="$(find_conda || true)"
    if [ -n "$CONDA_BIN" ]; then
        echo -e "  [${GREEN}FOUND${RESET}]   Conda CLI    : $CONDA_BIN"
        echo "[FOUNDATION] Conda: $CONDA_BIN" >> "$MANIFEST"
    else
        echo -e "  [${YELLOW}NOTE${RESET}]    Conda CLI    : Not detected. Using Python virtual environment (.env)."
        echo "[FOUNDATION] Conda: NOT DETECTED (Using python3 -m venv)" >> "$MANIFEST"
    fi

    # Hardware Detection
    HAS_NVIDIA=0
    GPU_MODEL="CPU Only (No NVIDIA GPU Detected)"
    if command -v nvidia-smi >/dev/null 2>&1; then
        DETECTED_GPU="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -n 1 || true)"
        if [ -n "$DETECTED_GPU" ]; then
            HAS_NVIDIA=1
            GPU_MODEL="$DETECTED_GPU"
        fi
    fi
    echo -e "  [${CYAN}SYSTEM${RESET}]  Hardware Target: $GPU_MODEL"
    echo "[HARDWARE] Detected Target: $GPU_MODEL" >> "$MANIFEST"

    # Prepare Environment
    ENV_NAME="lumiya"
    PY_BIN=""
    if [ -n "$CONDA_BIN" ]; then
        eval "$("$CONDA_BIN" shell.bash hook 2>/dev/null || true)"
        echo ""
        echo "  [01/05] Preparing Conda environment '$ENV_NAME'..."
        if conda info --envs 2>/dev/null | grep -qw "$ENV_NAME"; then
            echo "  [02/05] Using existing Conda environment '$ENV_NAME'..."
            echo "[ENV] Kept existing environment: $ENV_NAME" >> "$MANIFEST"
        else
            echo "  [02/05] Creating isolated Python 3.13 Conda environment '$ENV_NAME'..."
            conda create -n "$ENV_NAME" python=3.13 -c conda-forge --override-channels -y || conda create -n "$ENV_NAME" python=3.13 -y
            echo "[ENV] Created environment: $ENV_NAME (Python 3.13)" >> "$MANIFEST"
        fi
        conda activate "$ENV_NAME"
        PY_BIN="$(which python)"
    else
        echo ""
        echo "  [01/05] Preparing local Python virtual environment (.env)..."
        if [ ! -d "./.env" ]; then
            python3 -m venv .env
            echo "[ENV] Created local .env virtualenv" >> "$MANIFEST"
        else
            echo "[ENV] Kept existing .env virtualenv" >> "$MANIFEST"
        fi
        source ./.env/bin/activate
        PY_BIN="$(pwd)/.env/bin/python"
    fi

    "$PY_BIN" -m pip list --format=freeze > "$PRE_LIST" 2>/dev/null || true

    # Hardware-matched PyTorch installation
    echo "  [03/05] Installing hardware-matched PyTorch for [$GPU_MODEL]..."
    CUDA_LEVEL=0
    if [ "$HAS_NVIDIA" -eq 1 ]; then
        CUDA_VER_STR="$(nvidia-smi 2>/dev/null | grep -o 'CUDA Version: [0-9]\+\.[0-9]\+' | cut -d' ' -f3 || true)"
        if [ -n "$CUDA_VER_STR" ]; then
            MAJOR=$(echo "$CUDA_VER_STR" | cut -d'.' -f1)
            MINOR=$(echo "$CUDA_VER_STR" | cut -d'.' -f2)
            CUDA_LEVEL=$((MAJOR * 10 + MINOR))
        fi
    fi
    echo -e "  [${CYAN}SYSTEM${RESET}]  Driver CUDA level: $CUDA_LEVEL"

    TORCH_BUILD=""
    if [ "$CUDA_LEVEL" -ge 126 ]; then
        for ver in 132 130 128 126; do
            if [ "$CUDA_LEVEL" -ge "$ver" ] && [ -z "$TORCH_BUILD" ]; then
                if "$PY_BIN" -m pip install --no-cache-dir torch torchvision --index-url "https://download.pytorch.org/whl/cu$ver"; then
                    TORCH_BUILD="cu$ver"
                fi
            fi
        done
    fi

    if [ -z "$TORCH_BUILD" ]; then
        "$PY_BIN" -m pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
        TORCH_BUILD="cpu"
    fi
    echo "[HARDWARE] Torch build: $TORCH_BUILD" >> "$MANIFEST"

    # Core Dependencies
    echo "  [04/05] Installing pinned diffusion, image & telemetry packages..."
    "$PY_BIN" -m pip install --no-cache-dir \
        "diffusers>=0.30.0" \
        "transformers>=4.44.0" \
        "accelerate>=0.33.0" \
        "huggingface-hub>=0.24.0" \
        "safetensors>=0.4.3" \
        "Pillow>=10.3.0" \
        "psutil>=5.9.8" \
        "numpy>=1.26.0" \
        "pynvml>=11.5.0"

    "$PY_BIN" -m pip list --format=freeze > "$POST_LIST" 2>/dev/null || true

    # Manifest Output
    echo "" >> "$MANIFEST"
    echo "--- [1] TARGET SPECIFICATION ---" >> "$MANIFEST"
    echo "Python, torch ($TORCH_BUILD), torchvision, diffusers, transformers, accelerate, Pillow>=10.3.0, psutil>=5.9.8" >> "$MANIFEST"

    echo "" >> "$MANIFEST"
    echo "--- [2] KEPT PACKAGES ---" >> "$MANIFEST"
    cat "$PRE_LIST" | sed 's/^/  [KEPT] /' >> "$MANIFEST"

    echo "" >> "$MANIFEST"
    echo "--- [3] NEWLY INSTALLED PACKAGES ---" >> "$MANIFEST"
    grep -F -v -f "$PRE_LIST" "$POST_LIST" | sed 's/^/  [NEW]  /' >> "$MANIFEST" || echo "  (All target packages were already installed)" >> "$MANIFEST"

    echo "" >> "$MANIFEST"
    echo "--- [4] VERIFICATION MATRIX ---" >> "$MANIFEST"
    for pkg in torch torchvision diffusers transformers accelerate PIL psutil; do
        "$PY_BIN" -c "import $pkg; print('  [VERIFIED] $pkg ->', getattr($pkg, '__version__', 'OK'))" >> "$MANIFEST" 2>/dev/null || echo "  [MISSING]  $pkg" >> "$MANIFEST"
    done

    # Clean caches
    "$PY_BIN" -m pip cache purge >/dev/null 2>&1 || true
    if [ -n "$CONDA_BIN" ]; then
        conda clean --all -y >/dev/null 2>&1 || true
    fi
    find "$(pwd)" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

    echo ""
    echo "  ===================================================================================================="
    echo -e "  [${GREEN}COMPLETE${RESET}] Environment is ready. Manifest saved to:"
    echo "             user/install_manifest.log"
    echo "  ===================================================================================================="
    echo ""
}

do_uninstall() {
    print_banner
    echo -e "  [${RED}UNINSTALL${RESET}] Removing Lumiya's isolated dependencies (.env and Conda 'lumiya')."
    echo "  Personal photos in results/ and configurations in user/ will NOT be touched."
    echo ""
    if [ -f "$MANIFEST" ]; then
        echo "  --- Package Delta from install_manifest.log ---"
        grep -E "\[ENV\]|\[NEW\]" "$MANIFEST" || true
        echo "  -----------------------------------------------"
        echo ""
    fi

    CONFIRM_FLAG=0
    for arg in "$@"; do
        if [ "$arg" = "-y" ] || [ "$arg" = "--yes" ] || [ "$arg" = "-f" ] || [ "$arg" = "--force" ]; then
            CONFIRM_FLAG=1
        fi
    done

    if [ "$CONFIRM_FLAG" -eq 0 ]; then
        read -r -p "  Proceed with removing Lumiya isolated environment? [y/N] " confirm
        case "$confirm" in
            [yY][eE][sS]|[yY]) ;;
            *)
                echo "  Uninstallation aborted."
                exit 0
                ;;
        esac
    fi

    if [ -d "./.env" ]; then
        rm -rf ./.env
        echo -e "  [${GREEN}REMOVED${RESET}] Local .env directory deleted."
    fi
    CONDA_BIN="$(find_conda || true)"
    if [ -n "$CONDA_BIN" ]; then
        eval "$("$CONDA_BIN" shell.bash hook 2>/dev/null || true)"
        if conda info --envs 2>/dev/null | grep -qw "lumiya"; then
            conda env remove -n lumiya -y >/dev/null 2>&1 || true
            echo -e "  [${GREEN}REMOVED${RESET}] Conda environment 'lumiya' removed."
        fi
    fi
    echo -e "  [${GREEN}CLEAN${RESET}] Uninstallation complete."
    exit 0
}

do_clean() {
    print_banner
    echo -e "  [${CYAN}CLEAN${RESET}] Purging __pycache__, pip cache, and temporary files..."
    find "$(pwd)" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "$(pwd)" -type f -name "*.tmp" -delete 2>/dev/null || true
    find "$(pwd)" -type f -name "*.partial" -delete 2>/dev/null || true
    select_env_python
    if [ -n "$SELECTED_PY" ]; then
        "$SELECTED_PY" -m pip cache purge >/dev/null 2>&1 || true
    fi
    echo -e "  [${GREEN}DONE${RESET}] Workspace storage cleaned."
    exit 0
}

do_test() {
    print_banner
    echo -e "  [${CYAN}TEST${RESET}] Running core test suite..."
    select_env_python
    if [ -z "$SELECTED_PY" ]; then
        echo -e "  [${RED}ERROR${RESET}] No Python environment detected. Run ./run.sh install first."
        exit 1
    fi
    if [ -f "./__non-production__/tests/test_core.py" ]; then
        "$SELECTED_PY" "./__non-production__/tests/test_core.py" -v
    else
        echo -e "  [${YELLOW}NOTE${RESET}] Test runner not found at ./__non-production__/tests/test_core.py"
    fi
    find "$(pwd)" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    exit 0
}

do_status() {
    print_banner
    echo -e "  [${CYAN}SYSTEM AUDIT${RESET}] Hardware & Environment Telemetry:"
    check_distro
    if command -v git >/dev/null 2>&1; then
        echo -e "  Git          : $(git --version 2>/dev/null)"
    else
        echo -e "  Git          : Not installed"
    fi
    if command -v nvidia-smi >/dev/null 2>&1; then
        echo -e "  GPU          : $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -n 1)"
        echo -e "  Driver/CUDA  : $(nvidia-smi 2>/dev/null | grep -o 'CUDA Version: [0-9.]*' || true)"
    else
        echo -e "  GPU          : No NVIDIA GPU detected"
    fi
    select_env_python
    echo -e "  Python       : $SELECTED_PY ($("$SELECTED_PY" --version 2>/dev/null || echo 'Unknown'))"
    if [ -f "$MANIFEST" ]; then
        echo ""
        echo "  --- Last Installation Manifest ---"
        tail -n 12 "$MANIFEST"
    fi
    exit 0
}

# Omnipotent CLI argument & subcommand handling
case "$1" in
    install|--install|-i|setup)
        shift
        do_install "$@"
        exit 0
        ;;
    uninstall|--uninstall|-u|remove)
        shift
        do_uninstall "$@"
        exit 0
        ;;
    clean|--clean|-c)
        shift
        do_clean "$@"
        exit 0
        ;;
    test|--test|-t)
        shift
        do_test "$@"
        exit 0
        ;;
    status|--status)
        shift
        do_status "$@"
        exit 0
        ;;
    start|run)
        shift
        ;;
    help|--help|-h)
        print_banner
        echo "Usage: ./run.sh [SUBCOMMAND | OPTIONS] [ARGUMENTS...]"
        echo ""
        echo "Subcommands:"
        echo "  install, setup        Provision environment & install hardware-matched dependencies"
        echo "  uninstall, remove     Remove isolated Python environment (.env or Conda 'lumiya')"
        echo "  clean                 Purge cache and temporary workspace files"
        echo "  test                  Run the core offline test suite"
        echo "  status                Display hardware, driver, and environment audit"
        echo "  start, run            Launch the Lumiya WebUI backend server"
        echo ""
        echo "Options:"
        echo "  -i, --install         Same as 'install'"
        echo "  -u, --uninstall [-y]  Same as 'uninstall' (use -y for non-interactive)"
        echo "  -c, --clean           Same as 'clean'"
        echo "  -t, --test            Same as 'test'"
        echo "  -h, --help            Show this help reference"
        echo ""
        echo "All other arguments are passed directly to protect.py (e.g. --port 7860, --debug, --no-browser)."
        exit 0
        ;;
esac

# Default: Normal Launch & Pre-flight Inspection
print_banner
check_distro

if command -v git >/dev/null 2>&1; then
    echo -e "  [${GREEN}FOUND${RESET}]     Git CLI                : Installed in PATH"
else
    echo -e "  [${YELLOW}MISSING${RESET}]   Git CLI                : Not detected in PATH (Recommended: Git 2.45+)"
fi

select_env_python

# If environment not initialized with dependencies, prompt
if [ -z "$SELECTED_PY" ] || [ "$SELECTED_ENV" = "system (python3)" ]; then
    echo -e "  [${YELLOW}MISSING${RESET}]   Python Environment     : No initialized environment found"
    echo ""
    echo "  ===================================================================================================="
    echo -e "  ${YELLOW}[ENVIRONMENT NOT INITIALIZED]${RESET}"
    echo "    [I] Run environment installer now (setup dependencies & hardware-matched PyTorch)"
    echo "    [U] Uninstall existing broken environment"
    echo "    [W] Launch WebUI in limited mode (using system python3)"
    echo "    [Q] Exit"
    echo "  ===================================================================================================="
    read -r -p "  Select option [I / U / W / Q]: " opt
    case "$opt" in
        [iI])
            do_install
            select_env_python
            ;;
        [uU])
            do_uninstall
            exit 0
            ;;
        [wW])
            if command -v python3 >/dev/null 2>&1; then
                SELECTED_PY="$(which python3)"
                SELECTED_ENV="system (python3)"
            fi
            ;;
        *)
            exit 0
            ;;
    esac
fi

if [ -z "$SELECTED_PY" ]; then
    echo -e "  [${RED}FATAL${RESET}] No usable Python interpreter available."
    exit 1
fi

echo -e "  [${GREEN}ACTIVE${RESET}]    Environment            : $SELECTED_ENV"
echo "  ===================================================================================================="
echo ""

exec "$SELECTED_PY" protect.py "$@"
