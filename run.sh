#!/usr/bin/env bash
# ==============================================================================
# PORTtralica Lumiya v0.6.021.4330 (Pilot) - All-in-One Linux Launcher & Setup
# ==============================================================================
set -e
cd "$(dirname "$0")"

# Ensure CUDA runtime libraries are discoverable by dynamic linker across standard Linux paths
for p in /usr/lib/x86_64-linux-gnu /usr/lib64 /usr/local/cuda/lib64 /usr/lib/wsl/lib; do
    if [ -d "$p" ]; then
        case ":${LD_LIBRARY_PATH:-}:" in
            *:"$p":*) ;;
            *) LD_LIBRARY_PATH="${LD_LIBRARY_PATH:+$LD_LIBRARY_PATH:}$p" ;;
        esac
    fi
done
export LD_LIBRARY_PATH

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
    echo "                :::::::::::::                                                                         "
    echo "                :   :::::::::                                                                         "
    echo "                  :::                                            :::                                  "
    echo "                 ::                                              :::                                  "
    echo "                ::   :::       ::    ::  ::::::   ::::::       ::       ::::    :::      ::::::::     "
    echo "              :::   ::       :::     :::::   :: :::   ::     :::      :::      ::::   ::::      : :   "
    echo "             ::    ::       ::     ::::      :::     ::     :::      ::       ::::  :::        ::::   "
    echo "           :::    ::      :::    :::        ::      ::     ::      :::       :::   ::        :::    ::"
    echo "  :::::   ::     ::    :::::   :::        :::     ::    ::::    :::::      :::  :::::     ::::    ::: "
    echo "  :    :::       ::::::  ::::::::        ::       ::::::  :::::::  :::::::::::::   :::::::::::::::    "
    echo "   ::::::::       ::                                                     ::::                         "
    echo "          :::::   ::                                                 ::::::                           "
    echo "              :::::                                                :::::::                            "
    echo "                                                                :::: :::                              "
    echo "                                                               ::: ::::                               "
    echo "                                                               ::::::                                 "
    echo -e "${RESET}"
    echo -e "  ${DIM}PORTtralica Lumiya - v0.6.021.4330 (Pilot) - (c) 2026 PORTtralica Media Group${RESET}"
    echo "  ===================================================================================================="
    echo ""
}

find_conda() {
    if [ -n "${CONDA_EXE:-}" ] && [ -x "$CONDA_EXE" ]; then
        echo "$CONDA_EXE"
        return
    fi
    if type -P conda >/dev/null 2>&1; then
        type -P conda
        return
    fi
    for c in "$HOME/miniconda3/bin/conda" "$HOME/anaconda3/bin/conda" "$HOME/miniforge3/bin/conda" "/opt/conda/bin/conda" "/opt/miniconda3/bin/conda"; do
        if [ -x "$c" ]; then
            echo "$c"
            return
        fi
    done
}

ensure_linux_cuda_lib_path() {
    for lib_dir in /usr/lib/x86_64-linux-gnu /usr/lib64 /usr/local/cuda/lib64 /usr/lib/wsl/lib; do
        if [ -d "$lib_dir" ]; then
            case ":${LD_LIBRARY_PATH:-}:" in
                *":$lib_dir:"*) ;;
                *) export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:+$LD_LIBRARY_PATH:}$lib_dir" ;;
            esac
        fi
    done
}
ensure_linux_cuda_lib_path

check_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        case "$ID" in
            debian|ubuntu|linuxmint|pop)
                echo -e "  [${GREEN}VERIFIED${RESET}]  OS Distribution        : ${PRETTY_NAME:-$ID} (Debian/Ubuntu family)"
                ;;
            *)
                if echo "${ID_LIKE:-}" | grep -qE "debian|ubuntu"; then
                    echo -e "  [${GREEN}VERIFIED${RESET}]  OS Distribution        : ${PRETTY_NAME:-$ID} (Debian derivative)"
                else
                    echo -e "  [${YELLOW}CAUTION${RESET}]   OS Distribution        : ${PRETTY_NAME:-$ID}"
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

    CONDA_BIN="$(find_conda || true)"
    CONDA_ROOT=""
    if [ -n "$CONDA_BIN" ]; then
        CONDA_ROOT="$("$CONDA_BIN" info --base 2>/dev/null || true)"
    fi
    CONDA_ENV_DIR=""
    if [ -n "$CONDA_BIN" ]; then
        CONDA_ENV_DIR="$("$CONDA_BIN" info --envs 2>/dev/null | awk '$1 == "lumiya" {print $NF; exit}' || true)"
    fi

    # Build prioritized candidates: Conda 'lumiya' envs first, then local .env
    CANDIDATES=()
    [ -n "$CONDA_ENV_DIR" ] && CANDIDATES+=("$CONDA_ENV_DIR/bin/python:lumiya ($CONDA_ENV_DIR)")
    [ -n "$CONDA_ROOT" ] && CANDIDATES+=("$CONDA_ROOT/envs/lumiya/bin/python:lumiya ($CONDA_ROOT/envs/lumiya)")
    CANDIDATES+=("$HOME/.conda/envs/lumiya/bin/python:lumiya ($HOME/.conda/envs/lumiya)")
    CANDIDATES+=("$HOME/miniconda3/envs/lumiya/bin/python:lumiya ($HOME/miniconda3/envs/lumiya)")
    CANDIDATES+=("$HOME/anaconda3/envs/lumiya/bin/python:lumiya ($HOME/anaconda3/envs/lumiya)")
    [ -x "./.env/bin/python" ] && CANDIDATES+=("./.env/bin/python:.env (Local Virtual Environment)")

    HAS_NV=0
    for smi in nvidia-smi /usr/bin/nvidia-smi /usr/local/cuda/bin/nvidia-smi /opt/cuda/bin/nvidia-smi; do
        if command -v "$smi" >/dev/null 2>&1 || [ -x "$smi" ]; then
            HAS_NV=1
            break
        fi
    done

    FALLBACK_PY=""
    FALLBACK_ENV=""

    for cand_entry in "${CANDIDATES[@]}"; do
        cand="${cand_entry%%:*}"
        cand_desc="${cand_entry#*:}"
        if [ -n "$cand" ] && [ -x "$cand" ]; then
            if "$cand" -c "import importlib.util as u; raise SystemExit(0 if (u.find_spec('torch') and u.find_spec('diffusers') and u.find_spec('PIL')) else 1)" >/dev/null 2>&1; then
                if [ "$HAS_NV" -eq 1 ]; then
                    if "$cand" -c "import torch; raise SystemExit(0 if torch.cuda.is_available() else 1)" >/dev/null 2>&1; then
                        SELECTED_PY="$cand"
                        SELECTED_ENV="$cand_desc"
                        return
                    elif [ -z "$FALLBACK_PY" ]; then
                        FALLBACK_PY="$cand"
                        FALLBACK_ENV="$cand_desc"
                    fi
                else
                    SELECTED_PY="$cand"
                    SELECTED_ENV="$cand_desc"
                    return
                fi
            fi
        fi
    done

    if [ -n "$FALLBACK_PY" ]; then
        SELECTED_PY="$FALLBACK_PY"
        SELECTED_ENV="$FALLBACK_ENV"
        return
    fi

    # Fallback to system python3
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
    echo "  PORTtralica Lumiya v0.6.021.4330 (Pilot) - INSTALLATION MANIFEST" >> "$MANIFEST"
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
    NVIDIA_SMI="nvidia-smi"
    if ! command -v nvidia-smi >/dev/null 2>&1; then
        for smi in /usr/bin/nvidia-smi /usr/local/cuda/bin/nvidia-smi /opt/cuda/bin/nvidia-smi; do
            if [ -x "$smi" ]; then
                NVIDIA_SMI="$smi"
                break
            fi
        done
    fi
    if command -v "$NVIDIA_SMI" >/dev/null 2>&1 || [ -x "$NVIDIA_SMI" ]; then
        DETECTED_GPU="$("$NVIDIA_SMI" --query-gpu=name --format=csv,noheader 2>/dev/null | head -n 1 || true)"
        if [ -n "$DETECTED_GPU" ] && ! echo "$DETECTED_GPU" | grep -qiE "No devices|N/A|failed|error"; then
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
        CUDA_VER_STR="$("$NVIDIA_SMI" 2>/dev/null | sed -n 's/.*CUDA Version:[[:space:]]*\([0-9]\+\.[0-9]\+\).*/\1/p' | head -n 1 || true)"
        if [ -n "$CUDA_VER_STR" ]; then
            MAJOR=$(echo "$CUDA_VER_STR" | cut -d'.' -f1)
            MINOR=$(echo "$CUDA_VER_STR" | cut -d'.' -f2)
            CUDA_LEVEL=$((MAJOR * 10 + MINOR))
        fi
    fi
    echo -e "  [${CYAN}SYSTEM${RESET}]  Driver CUDA level: $CUDA_LEVEL"

    TORCH_BUILD=""
    if [ "$CUDA_LEVEL" -ge 118 ]; then
        for ver in 132 130 128 126 124 121 118; do
            if [ "$CUDA_LEVEL" -ge "$ver" ] && [ -z "$TORCH_BUILD" ]; then
                echo "  [03/05] Trying PyTorch CUDA wheel cu$ver..."
                if "$PY_BIN" -m pip install --force-reinstall --no-cache-dir torch torchvision --index-url "https://download.pytorch.org/whl/cu$ver"; then
                    if "$PY_BIN" -c "import torch; raise SystemExit(0 if torch.cuda.is_available() else 1)" 2>/dev/null; then
                        TORCH_BUILD="cu$ver"
                        echo -e "  [${GREEN}VERIFIED${RESET}] PyTorch cu$ver initialized CUDA successfully on [$GPU_MODEL]."
                        break
                    else
                        echo -e "  [${YELLOW}FALLBACK${RESET}] PyTorch cu$ver installed but driver rejected runtime; stepping down to older CUDA wheel..."
                    fi
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
    if [ "$TORCH_BUILD" != "cpu" ] && [ -n "$TORCH_BUILD" ]; then
        "$PY_BIN" -m pip install --no-cache-dir \
            --extra-index-url "https://download.pytorch.org/whl/$TORCH_BUILD" \
            "diffusers>=0.30.0" \
            "transformers>=4.44.0" \
            "accelerate>=0.33.0" \
            "huggingface-hub>=0.24.0" \
            "safetensors>=0.4.3" \
            "Pillow>=10.3.0" \
            "psutil>=5.9.8" \
            "numpy>=1.26.0" \
            "pynvml>=11.5.0"
    else
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
    fi

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
    UNINSTALL_MODE="MANIFEST"
    CONFIRM_FLAG=0

    for arg in "$@"; do
        case "$arg" in
            -h|--help)
                echo "Usage: ./run.sh uninstall [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --uninstall, -u       Remove this program footprint dependencies (default: manifest cleanup)"
                echo "  --purge, -p           Thoroughly purge runtime pillars"
                echo "  -y, --yes             Skip interactive confirmations"
                echo "  -h, --help            Show this help reference"
                echo ""
                echo "Default Mode (without --purge):"
                echo "  Performs manifest-based cleanup: removes this program footprint dependencies"
                echo "  (.env & Conda 'lumiya') while keeping your exported photos (results/) and configurations (user/) safe."
                echo ""
                echo "Note:"
                echo "  The program folder itself is ALWAYS kept intact so you can manage,"
                echo "  back up, or delete remaining files at your discretion."
                exit 0
                ;;
            --purge|-p|purge|--all)
                UNINSTALL_MODE="PURGE"
                ;;
            --manifest|-m|manifest)
                UNINSTALL_MODE="MANIFEST"
                ;;
            -y|--yes|-f|--force)
                CONFIRM_FLAG=1
                ;;
        esac
    done

    if [ "$UNINSTALL_MODE" = "PURGE" ]; then
        echo -e "  ===================================================================================================="
        echo -e "  [${RED}WARNING // THOROUGH PURGE SELECTED${RESET}]"
        echo "  This will PERMANENTLY purge all runtime pillars:"
        echo "    - Conda environment 'lumiya' and local .env"
        echo "    - Pip/Conda package caches and temporary runtime data"
        echo ""
        echo "  The program folder itself and your exported photos (results/)"
        echo "  are ALWAYS KEPT intact."
        echo "  Pre-existing system foundations (Git, Miniconda, base Python) stay intact."
        echo "  ===================================================================================================="
        echo ""
        if [ "$CONFIRM_FLAG" -eq 0 ]; then
            read -r -p "  Are you sure you want to purge all runtime environments and caches? [y/N] " confirm
            case "$confirm" in
                [yY][eE][sS]|[yY]) ;;
                *)
                    echo "  Uninstallation aborted."
                    exit 0
                    ;;
            esac
        fi
        echo ""
        echo -e "  [${YELLOW}5-SECOND SAFETY COUNTDOWN${RESET}] Press Ctrl+C to cancel if this was chosen by mistake..."
        for sec in 5 4 3 2 1; do
            echo -ne "  Purging runtime pillars in $sec second(s)... (Press Ctrl+C to abort)\r"
            sleep 1
        done
        echo ""
    else
        echo -e "  [${CYAN}MANIFEST CLEANUP // DEFAULT MODE${RESET}]"
        echo "  Removing Lumiya's isolated dependencies (.env and Conda 'lumiya' environment)."
        echo "  User configurations (user/) and exported photos (results/) will be KEPT."
        echo ""
        if [ -f "$MANIFEST" ]; then
            echo "  --- Recorded Delta from install_manifest.log ---"
            grep -E "\[ENV\]|\[NEW\]" "$MANIFEST" 2>/dev/null || true
            echo "  -----------------------------------------------"
            echo ""
        fi
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
    fi

    echo ""
    echo "  Removing local .env virtual environment..."
    if [ -d "./.env" ]; then
        rm -rf ./.env
        echo -e "  [${GREEN}REMOVED${RESET}] Local .env directory deleted."
    fi

    echo "  Removing Conda environment 'lumiya'..."
    CONDA_BIN="$(find_conda || true)"
    if [ -n "$CONDA_BIN" ]; then
        eval "$("$CONDA_BIN" shell.bash hook 2>/dev/null || true)"
        CONDA_ENV_DIR="$("$CONDA_BIN" info --envs 2>/dev/null | awk '$1 == "lumiya" {print $NF; exit}' || true)"
        CONDA_ROOT="$("$CONDA_BIN" info --base 2>/dev/null || true)"
        conda env remove -n lumiya -y >/dev/null 2>&1 || true
        for d in "$CONDA_ENV_DIR" "${CONDA_ROOT:+$CONDA_ROOT/envs/lumiya}" "$HOME/.conda/envs/lumiya" "$HOME/miniconda3/envs/lumiya" "$HOME/anaconda3/envs/lumiya"; do
            if [ -n "$d" ] && [ -d "$d" ]; then
                rm -rf "$d"
            fi
        done
        conda clean --all -y >/dev/null 2>&1 || true
        echo -e "  [${GREEN}REMOVED${RESET}] Conda environment 'lumiya' removed."
    fi

    find "$(pwd)" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

    if [ "$UNINSTALL_MODE" = "PURGE" ]; then
        echo "  Purging runtime manifest and temporary logs..."
        rm -f ./user/install_manifest.log ./user/history.json 2>/dev/null || true
        echo ""
        echo "  ===================================================================================================="
        echo -e "  [${GREEN}COMPLETE${RESET}] Thorough uninstallation finished."
        echo "  All runtime pillars (Conda 'lumiya' environment, .env, and caches)"
        echo "  have been purged."
        echo ""
        echo "  The program folder and your exported photos (results/) were kept intact"
        echo "  so you can manage remaining data at your discretion."
        echo "  ===================================================================================================="
        exit 0
    fi

    echo ""
    echo "  ===================================================================================================="
    echo -e "  [${GREEN}CLEAN${RESET}] Uninstallation complete. Isolated environment removed."
    echo "  The program folder and exported photos (results/) were preserved."
    echo "  ===================================================================================================="
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
    purge|--purge|-p)
        shift
        do_uninstall --purge "$@"
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
        echo "  uninstall, remove     Remove this program footprint dependencies (default: manifest cleanup)"
        echo "  purge                 Thoroughly purge runtime pillars"
        echo "  clean                 Purge cache and temporary workspace files"
        echo "  test                  Run the core offline test suite"
        echo "  status                Display hardware, driver, and environment audit"
        echo "  start, run            Launch the Lumiya WebUI backend server"
        echo ""
        echo "Options:"
        echo "  -i, --install         Same as 'install'"
        echo "  -u, --uninstall [-y]  Remove this program footprint dependencies (default: manifest cleanup)"
        echo "  -p, --purge [-y]      Thoroughly purge runtime pillars"
        echo "  -c, --clean           Same as 'clean'"
        echo "  -t, --test            Same as 'test'"
        echo "  -h, --help            Show this help reference"
        echo ""
        echo "All other arguments are passed directly to protect.py (e.g. --port 7860, --debug, --no-browser)."
        exit 0
        ;;
esac

# Default: Normal Launch & Pre-flight Inspection
trap 'echo -e "\n  [SHUTDOWN] Exiting Lumiya launcher (Ctrl+C)..."; exit 0' INT TERM
print_banner
check_distro

if command -v git >/dev/null 2>&1; then
    echo -e "  [${GREEN}FOUND${RESET}]     Git CLI                : Installed in PATH"
else
    echo -e "  [${YELLOW}MISSING${RESET}]   Git CLI                : Not detected in PATH (Recommended: Git 2.45+)"
fi

GPU_INFO="CPU Only (No NVIDIA GPU detected)"
if command -v nvidia-smi >/dev/null 2>&1; then
    GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -n 1 || true)"
    CUDA_V="$(nvidia-smi 2>/dev/null | sed -n 's/.*CUDA Version:[[:space:]]*\([0-9]\+\.[0-9]\+\).*/\1/p' | head -n 1 || true)"
    if [ -n "$GPU_NAME" ]; then
        GPU_INFO="$GPU_NAME (Driver CUDA $CUDA_V)"
    fi
fi
echo -e "  [${CYAN}TARGET${RESET}]    Hardware / CUDA        : $GPU_INFO"

select_env_python

# If environment not initialized with dependencies, prompt
if [ -z "$SELECTED_PY" ] || [ "$SELECTED_ENV" = "system (python3)" ]; then
    echo -e "  [${YELLOW}MISSING${RESET}]   Python Environment     : No initialized environment found"
    echo ""
    echo "  ===================================================================================================="
    echo -e "  ${YELLOW}[ENVIRONMENT NOT INITIALIZED]${RESET}"
    echo "    [I] Run environment installer now (setup dependencies & hardware-matched PyTorch)"
    echo "    [W] Launch WebUI in limited mode (using system python3)"
    echo "    [Q] Exit"
    echo "  ===================================================================================================="
    read -r -p "  Select option [I / W / Q]: " opt
    case "$opt" in
        [iI])
            do_install
            select_env_python
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
