#!/usr/bin/env bash
# ==============================================================================
# PORTtralica Lumiya v0.6.073.8820 (Pilot) - All-in-One Linux Launcher & Setup
# ==============================================================================
set -e
cd "$(dirname "$0")"

# Ensure CUDA and NVML runtime libraries are discoverable across Debian/Ubuntu, Fedora/RHEL, Arch, openSUSE, NixOS, and WSL2
for p in /usr/lib/x86_64-linux-gnu /usr/lib64 /usr/lib64/nvidia /usr/lib /opt/cuda/lib64 /usr/local/cuda/lib64 /usr/local/cuda/targets/x86_64-linux/lib /run/opengl-driver/lib /usr/lib/wsl/lib; do
    if [ -d "$p" ]; then
        case ":${LD_LIBRARY_PATH:-}:" in
            *:"$p":*) ;;
            *) LD_LIBRARY_PATH="${LD_LIBRARY_PATH:+$LD_LIBRARY_PATH:}$p" ;;
        esac
    fi
done
export LD_LIBRARY_PATH

TMPDIR_REASON="System default"
ensure_smart_tmpdir() {
    local force_cluster="${1:-0}"
    local target_tmp="${TMPDIR:-/tmp}"
    if [ -n "${LUMIYA_TMP_DIR:-}" ]; then
        export TMPDIR="$LUMIYA_TMP_DIR"
        mkdir -p "$TMPDIR"
        TMPDIR_REASON="Custom (--tmp-dir)"
        return
    fi
    local need_fallback=0
    if [ "$force_cluster" -eq 1 ] || [ -n "${SLURM_JOB_ID:-}" ] || [ -n "${PBS_JOBID:-}" ]; then
        need_fallback=1
        TMPDIR_REASON="Cluster mode preset"
    elif [ ! -d "$target_tmp" ] || [ ! -w "$target_tmp" ]; then
        need_fallback=1
        TMPDIR_REASON="/tmp not writable"
    else
        local avail_mb
        avail_mb="$(df -Pm "$target_tmp" 2>/dev/null | awk 'NR==2 {print $4}' || echo 99999)"
        if [ -n "$avail_mb" ] && [ "$avail_mb" -lt 4096 ] 2>/dev/null; then
            need_fallback=1
            TMPDIR_REASON="/tmp free space < 4GB (${avail_mb}MB)"
        elif command -v quota >/dev/null 2>&1; then
            local tmp_dev quota_rem_kb
            tmp_dev="$(df -P "$target_tmp" 2>/dev/null | awk 'NR==2 {print $1}' || true)"
            if [ -n "$tmp_dev" ]; then
                quota_rem_kb="$(quota -w 2>/dev/null | awk -v dev="$tmp_dev" '$1 == dev && $3 > 0 {print $3 - $2}' || true)"
                if [ -n "$quota_rem_kb" ] && [ "$quota_rem_kb" -lt 4194304 ] 2>/dev/null; then
                    need_fallback=1
                    TMPDIR_REASON="/tmp user quota < 4GB ($((quota_rem_kb / 1024))MB remaining on $tmp_dev)"
                fi
            fi
        fi
    fi
    if [ "$need_fallback" -eq 1 ]; then
        export TMPDIR="${XDG_CACHE_HOME:-$HOME/.cache}/lumiya_tmp"
        mkdir -p "$TMPDIR"
    fi
}
ensure_smart_tmpdir 0

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
ERRLOG="$USER_DIR/error.log"

log_err() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [run.sh] $*" >> "$ERRLOG" 2>/dev/null || true
}

print_banner() {
    local sub_title="${1:-PORTtralica Lumiya - v0.6.073.8820 (Pilot) - (c) 2026 PORTtralica Media Group}"
    echo ""
    echo -e "  ${LOGO_GOLD}              :::::::::::::                                                                         ${RESET}"
    echo -e "  ${LOGO_GOLD}              :   :::::::::                                                                         ${RESET}"
    echo -e "  ${LOGO_GOLD}                :::                                            :::                                  ${RESET}"
    echo -e "  ${LOGO_GOLD}               ::                                              :::                                  ${RESET}"
    echo -e "  ${LOGO_GOLD}              ::   :::       ::    ::  ::::::   ::::::       ::       ::::    :::      ::::::::     ${RESET}"
    echo -e "  ${LOGO_GOLD}            :::   ::       :::     :::::   :: :::   ::     :::      :::      ::::   ::::      : :   ${RESET}"
    echo -e "  ${LOGO_GOLD}           ::    ::       ::     ::::      :::     ::     :::      ::       ::::  :::        ::::   ${RESET}"
    echo -e "  ${LOGO_GOLD}         :::    ::      :::    :::        ::      ::     ::      :::       :::   ::        :::    ::${RESET}"
    echo -e "  ${LOGO_GOLD}:::::   ::     ::    :::::   :::        :::     ::    ::::    :::::      :::  :::::     ::::    ::: ${RESET}"
    echo -e "  ${LOGO_GOLD}:    :::       ::::::  ::::::::        ::       ::::::  :::::::  :::::::::::::   :::::::::::::::    ${RESET}"
    echo -e "  ${LOGO_GOLD} ::::::::       ::                                                     ::::                         ${RESET}"
    echo -e "  ${LOGO_GOLD}        :::::   ::                                                 ::::::                           ${RESET}"
    echo -e "  ${LOGO_GOLD}            :::::                                                :::::::                            ${RESET}"
    echo -e "  ${LOGO_GOLD}                                                              :::: :::                              ${RESET}"
    echo -e "  ${LOGO_GOLD}                                                             ::: ::::                               ${RESET}"
    echo -e "  ${LOGO_GOLD}                                                             ::::::                                 ${RESET}"
    echo ""
    echo -e "  ${DIM}${sub_title}${RESET}"
    echo "  ===================================================================================================="
}

find_nvidia_smi() {
    if command -v nvidia-smi >/dev/null 2>&1; then
        command -v nvidia-smi
        return
    fi
    for smi in /usr/bin/nvidia-smi /usr/local/cuda/bin/nvidia-smi /opt/cuda/bin/nvidia-smi; do
        if [ -x "$smi" ]; then
            echo "$smi"
            return
        fi
    done
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

bootstrap_miniconda() {
    local target_dir="$HOME/miniconda3"
    local arch
    arch="$(uname -m 2>/dev/null || echo x86_64)"
    local installer_url="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-${arch}.sh"
    local installer_sh="${TMPDIR:-/tmp}/lumiya_miniconda_installer.sh"
    echo -e "  [${CYAN}BOOTSTRAP${RESET}] Provisioning Miniconda3 into \"$target_dir\"..."
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$installer_url" -o "$installer_sh"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO "$installer_sh" "$installer_url"
    elif command -v python3 >/dev/null 2>&1; then
        python3 -c "import urllib.request; urllib.request.urlretrieve('$installer_url', '$installer_sh')"
    else
        echo -e "  [${RED}ERROR${RESET}]     Cannot download Miniconda3 (curl, wget, and python3 are all missing)."
        return 1
    fi
    bash "$installer_sh" -b -u -p "$target_dir"
    rm -f "$installer_sh"
    if [ -x "$target_dir/bin/conda" ]; then
        "$target_dir/bin/conda" init bash >/dev/null 2>&1 || true
        echo -e "  [${GREEN}INSTALLED${RESET}] Miniconda3 installed at \"$target_dir\"."
        return 0
    fi
    return 1
}

check_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        local wsl_tag=""
        if grep -qiE "microsoft|wsl" /proc/version 2>/dev/null; then
            wsl_tag=" [WSL2]"
        fi
        local combined="${ID:-} ${ID_LIKE:-}"
        if echo "$combined" | grep -qiE "debian|ubuntu|linuxmint|pop|kali|zorin|elementary|raspbian"; then
            echo -e "  [${GREEN}VERIFIED${RESET}]  OS Distribution        : ${PRETTY_NAME:-$ID} (Debian/Ubuntu family)${wsl_tag}"
        elif echo "$combined" | grep -qiE "fedora|rhel|centos|rocky|almalinux|ol|nobara|bazzite"; then
            echo -e "  [${GREEN}VERIFIED${RESET}]  OS Distribution        : ${PRETTY_NAME:-$ID} (Fedora/RHEL family)${wsl_tag}"
        elif echo "$combined" | grep -qiE "arch|manjaro|endeavouros|garuda|cachyos|artix"; then
            echo -e "  [${GREEN}VERIFIED${RESET}]  OS Distribution        : ${PRETTY_NAME:-$ID} (Arch Linux family)${wsl_tag}"
        elif echo "$combined" | grep -qiE "opensuse|suse|sles"; then
            echo -e "  [${GREEN}VERIFIED${RESET}]  OS Distribution        : ${PRETTY_NAME:-$ID} (openSUSE/SUSE family)${wsl_tag}"
        elif echo "$combined" | grep -qiE "gentoo|nixos|void|alpine"; then
            echo -e "  [${GREEN}VERIFIED${RESET}]  OS Distribution        : ${PRETTY_NAME:-$ID} (Linux 64-bit)${wsl_tag}"
        else
            echo -e "  [${CYAN}DETECTED${RESET}]  OS Distribution        : ${PRETTY_NAME:-$ID}${wsl_tag}"
        fi
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

    # Build prioritized candidates: Conda 'lumiya' envs only (strict Conda requirement)
    CANDIDATES=()
    [ -n "$CONDA_ENV_DIR" ] && CANDIDATES+=("$CONDA_ENV_DIR/bin/python:lumiya (\"$CONDA_ENV_DIR/bin/python\")")
    [ -n "$CONDA_ROOT" ] && CANDIDATES+=("$CONDA_ROOT/envs/lumiya/bin/python:lumiya (\"$CONDA_ROOT/envs/lumiya/bin/python\")")
    CANDIDATES+=("$HOME/.conda/envs/lumiya/bin/python:lumiya (\"$HOME/.conda/envs/lumiya/bin/python\")")
    CANDIDATES+=("$HOME/miniconda3/envs/lumiya/bin/python:lumiya (\"$HOME/miniconda3/envs/lumiya/bin/python\")")
    CANDIDATES+=("$HOME/anaconda3/envs/lumiya/bin/python:lumiya (\"$HOME/anaconda3/envs/lumiya/bin/python\")")
    CANDIDATES+=("$HOME/miniforge3/envs/lumiya/bin/python:lumiya (\"$HOME/miniforge3/envs/lumiya/bin/python\")")

    HAS_NV=0
    SMI_BIN="$(find_nvidia_smi || true)"
    if [ -n "$SMI_BIN" ]; then
        HAS_NV=1
    fi

    FALLBACK_PY=""
    FALLBACK_ENV=""

    for cand_entry in "${CANDIDATES[@]}"; do
        cand="${cand_entry%%:*}"
        cand_desc="${cand_entry#*:}"
        if [ -n "$cand" ] && [ -x "$cand" ]; then
            if "$cand" -c "import importlib.util as u; raise SystemExit(0 if (u.find_spec('torch') and u.find_spec('diffusers') and u.find_spec('PIL')) else 1)" >/dev/null 2>&1; then
                if [ "$HAS_NV" -eq 1 ]; then
                    if "$cand" -c "import torch; raise SystemExit(0 if (torch.cuda.is_available() or getattr(torch.version, 'cuda', None) is not None) else 1)" >/dev/null 2>&1; then
                        SELECTED_PY="$cand"
                        SELECTED_ENV="$cand_desc"
                        return
                    elif [ -z "$FALLBACK_PY" ]; then
                        FALLBACK_PY="$cand"
                        FALLBACK_ENV="$cand_desc"
                        log_err "Environment '$cand' has PyTorch without CUDA build tag; marked as fallback."
                    fi
                else
                    SELECTED_PY="$cand"
                    SELECTED_ENV="$cand_desc"
                    return
                fi
            else
                log_err "Candidate interpreter '$cand' is missing torch, diffusers, or PIL."
            fi
        fi
    done

    if [ -n "$FALLBACK_PY" ]; then
        SELECTED_PY="$FALLBACK_PY"
        SELECTED_ENV="$FALLBACK_ENV"
        return
    fi
}

do_install() {
    print_banner "PORTtralica Lumiya v0.6.073.8820 (Pilot) - SYSTEM AUDIT & INSTALLER"
    PRE_LIST="$(mktemp "${TMPDIR:-/tmp}/lumiya_pre.XXXXXX.txt")"
    POST_LIST="$(mktemp "${TMPDIR:-/tmp}/lumiya_post.XXXXXX.txt")"
    trap 'rm -f "$PRE_LIST" "$POST_LIST"' EXIT

    echo "========================================================================" > "$MANIFEST"
    echo "  PORTtralica Lumiya v0.6.073.8820 (Pilot) - INSTALLATION MANIFEST" >> "$MANIFEST"
    echo "  Timestamp : $(date '+%Y-%m-%d %H:%M:%S')" >> "$MANIFEST"
    echo "  Username  : $(whoami 2>/dev/null || echo "$USER")" >> "$MANIFEST"
    echo "========================================================================" >> "$MANIFEST"

    # Foundation Checks
    check_distro
    if command -v git >/dev/null 2>&1; then
        echo -e "  [${GREEN}OK${RESET}]        Git CLI detected ($(which git))."
        echo "[FOUNDATION] Git CLI: Installed ($(git --version 2>/dev/null || true))" >> "$MANIFEST"
    else
        echo -e "  [${YELLOW}WARN${RESET}]      Git CLI not found in PATH."
        echo "[FOUNDATION] Git CLI: MISSING" >> "$MANIFEST"
    fi

    # Remove any legacy local .env virtualenv so it never shadows Conda
    if [ -d "./.env" ]; then
        rm -rf ./.env
    fi

    CONDA_BIN="$(find_conda || true)"
    if [ -z "$CONDA_BIN" ]; then
        echo -e "  [${YELLOW}MISSING${RESET}]   Conda Manager          : Not detected. Bootstrapping Miniconda3 automatically..."
        if bootstrap_miniconda; then
            CONDA_BIN="$(find_conda || true)"
            echo "[FOUNDATION] Conda: Auto-installed Miniconda3 ($CONDA_BIN)" >> "$MANIFEST"
        fi
    fi

    if [ -n "$CONDA_BIN" ]; then
        echo -e "  [${GREEN}OK${RESET}]        Conda located at: \"$CONDA_BIN\""
        echo "[FOUNDATION] Conda: \"$CONDA_BIN\"" >> "$MANIFEST"
    else
        echo -e "  [${RED}MISSING${RESET}]   Miniconda3 / Anaconda3 could not be installed automatically."
        echo "[FOUNDATION] Conda: MISSING" >> "$MANIFEST"
        echo ""
        echo "  ===================================================================================================="
        echo -e "  ${RED}[INSTALLATION HALTED // MISSING REQUIRED CONDA FOUNDATION]${RESET}"
        echo "  Please install Miniconda3 (64-bit) from https://docs.conda.io/en/latest/miniconda.html"
        echo "  and run './run.sh install' again."
        echo "  ===================================================================================================="
        exit 1
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
    echo -e "  [${CYAN}SYSTEM${RESET}]    Hardware Target: $GPU_MODEL"
    echo "[HARDWARE] Detected Target: $GPU_MODEL" >> "$MANIFEST"

    # Prepare Conda Environment
    ENV_NAME="lumiya"
    PY_BIN=""
    eval "$("$CONDA_BIN" shell.bash hook 2>/dev/null || true)"
    echo ""
    echo "  [01/05] Accepting Conda channel terms & preparing isolated install..."
    "$CONDA_BIN" tos accept >/dev/null 2>&1 || true
    "$CONDA_BIN" tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main >/dev/null 2>&1 || true
    "$CONDA_BIN" tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r >/dev/null 2>&1 || true
    if "$CONDA_BIN" info --envs 2>/dev/null | grep -qw "$ENV_NAME"; then
        echo "  [02/05] Using existing environment '$ENV_NAME'..."
        echo "[ENV] Kept existing environment: $ENV_NAME" >> "$MANIFEST"
    else
        echo "  [02/05] Creating isolated Python 3.12 environment '$ENV_NAME'..."
        "$CONDA_BIN" create -n "$ENV_NAME" python=3.12 -c conda-forge --override-channels -y || "$CONDA_BIN" create -n "$ENV_NAME" python=3.12 -y || "$CONDA_BIN" create -n "$ENV_NAME" python=3.13 -c conda-forge --override-channels -y
        echo "[ENV] Created environment: $ENV_NAME" >> "$MANIFEST"
    fi
    conda activate "$ENV_NAME" 2>/dev/null || true
    CONDA_ENV_DIR="$("$CONDA_BIN" info --envs 2>/dev/null | awk '$1 == "lumiya" {print $NF; exit}' || true)"
    CONDA_BASE_DIR="$("$CONDA_BIN" info --base 2>/dev/null || dirname "$(dirname "$CONDA_BIN")")"
    for cand_py in "${CONDA_ENV_DIR:+$CONDA_ENV_DIR/bin/python}" "${CONDA_BASE_DIR:+$CONDA_BASE_DIR/envs/lumiya/bin/python}" "$HOME/.conda/envs/lumiya/bin/python" "$HOME/miniconda3/envs/lumiya/bin/python" "$HOME/anaconda3/envs/lumiya/bin/python" "$HOME/miniforge3/envs/lumiya/bin/python" "$(command -v python 2>/dev/null || true)"; do
        if [ -n "$cand_py" ] && [ -x "$cand_py" ]; then
            PY_BIN="$cand_py"
            break
        fi
    done

    echo -e "  [${CYAN}PYTHON${RESET}]    Target Interpreter: $PY_BIN ($("$PY_BIN" --version 2>/dev/null || true))"
    "$PY_BIN" -m pip install --upgrade pip >/dev/null 2>&1 || true
    "$PY_BIN" -m pip list --format=freeze > "$PRE_LIST" 2>/dev/null || true

    # Hardware-matched PyTorch installation
    echo "  [03/05] Installing hardware-matched PyTorch for [$GPU_MODEL]..."
    CUDA_LEVEL=0
    if [ "$HAS_NVIDIA" -eq 1 ]; then
        CUDA_VER_STR="$("$NVIDIA_SMI" 2>/dev/null | grep -oE 'CUDA Version:[[:space:]]*[0-9]+\.[0-9]+' | grep -oE '[0-9]+\.[0-9]+' | head -n 1 || true)"
        if [ -z "$CUDA_VER_STR" ]; then
            DRV_VER="$("$NVIDIA_SMI" --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -n 1 | cut -d'.' -f1 || true)"
            if [ -n "$DRV_VER" ] && [ "$DRV_VER" -ge 570 ] 2>/dev/null; then
                CUDA_VER_STR="12.8"
            elif [ -n "$DRV_VER" ] && [ "$DRV_VER" -ge 560 ] 2>/dev/null; then
                CUDA_VER_STR="12.6"
            elif [ -n "$DRV_VER" ] && [ "$DRV_VER" -ge 550 ] 2>/dev/null; then
                CUDA_VER_STR="12.4"
            elif [ -n "$DRV_VER" ] && [ "$DRV_VER" -ge 530 ] 2>/dev/null; then
                CUDA_VER_STR="12.1"
            else
                CUDA_VER_STR="12.4"
            fi
        fi
        if [ -n "$CUDA_VER_STR" ]; then
            MAJOR="$(echo "$CUDA_VER_STR" | cut -d'.' -f1 | tr -cd '0-9')"
            MINOR="$(echo "$CUDA_VER_STR" | cut -d'.' -f2 | tr -cd '0-9')"
            CUDA_LEVEL=$(( ${MAJOR:-12} * 10 + ${MINOR:-4} ))
        else
            CUDA_LEVEL=126
        fi
    fi
    echo -e "  [${CYAN}SYSTEM${RESET}]  Driver CUDA level: $CUDA_LEVEL (stepping descending: cu132 -> cu130 -> cu128 -> cu126 -> cu124 -> cu121 -> cu118)"

    TORCH_BUILD=""
    if [ "$HAS_NVIDIA" -eq 1 ]; then
        for ver in 132 130 128 126 124 121 118; do
            if [ "$CUDA_LEVEL" -ge "$ver" ] && [ -z "$TORCH_BUILD" ]; then
                echo "  [03/05] Querying https://download.pytorch.org/whl/cu$ver for PyTorch CUDA wheel cu$ver..."
                if "$PY_BIN" -m pip install --upgrade --force-reinstall --no-cache-dir torch torchvision --index-url "https://download.pytorch.org/whl/cu$ver"; then
                    if "$PY_BIN" -c "import torch; raise SystemExit(0 if (torch.cuda.is_available() or getattr(torch.version, 'cuda', None) is not None) else 1)"; then
                        TORCH_BUILD="cu$ver"
                        echo -e "  [${GREEN}VERIFIED${RESET}] PyTorch cu$ver installed for [$GPU_MODEL]."
                        break
                    else
                        echo -e "  [${YELLOW}FALLBACK${RESET}] PyTorch cu$ver installed without CUDA build tag; stepping down to next wheel..."
                        log_err "PyTorch cu$ver installed but CUDA runtime check failed; stepping down."
                    fi
                else
                    echo -e "  [${DIM}SKIP${RESET}]     PyTorch wheel index cu$ver not yet published for this Python/OS; stepping down..."
                    log_err "Wheel index https://download.pytorch.org/whl/cu$ver unavailable; stepping down."
                fi
            fi
        done
        # If driver version was older than 118 or specific index failed, force cu126..cu118 before ever touching CPU
        if [ -z "$TORCH_BUILD" ]; then
            for fallback_ver in 126 124 121 118; do
                echo "  [03/05] Trying fallback PyTorch CUDA wheel cu$fallback_ver..."
                if "$PY_BIN" -m pip install --upgrade --force-reinstall --no-cache-dir torch torchvision --index-url "https://download.pytorch.org/whl/cu$fallback_ver"; then
                    if "$PY_BIN" -c "import torch; raise SystemExit(0 if getattr(torch.version, 'cuda', None) is not None else 1)"; then
                        TORCH_BUILD="cu$fallback_ver"
                        echo -e "  [${GREEN}VERIFIED${RESET}] PyTorch cu$fallback_ver installed for [$GPU_MODEL]."
                        break
                    fi
                fi
            done
        fi
    fi

    if [ -z "$TORCH_BUILD" ]; then
        log_err "Falling back to CPU PyTorch build (HAS_NVIDIA=$HAS_NVIDIA, CUDA_LEVEL=$CUDA_LEVEL)."
        "$PY_BIN" -m pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
        TORCH_BUILD="cpu"
    fi
    echo "[HARDWARE] Torch build: $TORCH_BUILD" >> "$MANIFEST"

    # Core Dependencies
    echo "  [04/05] Installing pinned diffusion, image & telemetry packages..."
    if [ "$TORCH_BUILD" != "cpu" ] && [ -n "$TORCH_BUILD" ]; then
        "$PY_BIN" -m pip install --no-cache-dir \
            --index-url "https://download.pytorch.org/whl/$TORCH_BUILD" \
            --extra-index-url https://pypi.org/simple \
            "diffusers>=0.30.0" \
            "transformers>=4.44.0" \
            "accelerate>=0.33.0" \
            "huggingface-hub>=0.24.0" \
            "safetensors>=0.4.3" \
            "Pillow>=10.3.0" \
            "psutil>=5.9.8" \
            "numpy>=1.26.0" \
            "nvidia-ml-py>=12.535.133"
        # Ensure step 4 never silently swapped CUDA torch for a PyPI CPU wheel
        if ! "$PY_BIN" -c "import torch; raise SystemExit(0 if getattr(torch.version, 'cuda', None) is not None else 1)" 2>/dev/null; then
            "$PY_BIN" -m pip install --upgrade --force-reinstall --no-deps --no-cache-dir torch torchvision --index-url "https://download.pytorch.org/whl/$TORCH_BUILD"
        fi
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
            "nvidia-ml-py>=12.535.133"
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
    echo "  [05/05] Purging installer caches & temporary files..."
    "$PY_BIN" -m pip cache purge >/dev/null 2>&1 || true
    if [ -n "$CONDA_BIN" ]; then
        "$CONDA_BIN" clean --all -y >/dev/null 2>&1 || true
    fi
    find "$(pwd)" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

    echo ""
    echo "  ===================================================================================================="
    echo -e "  [${GREEN}COMPLETE${RESET}] Environment '$ENV_NAME' is ready. Manifest saved to:"
    echo "             user/install_manifest.log"
    echo "  ===================================================================================================="
    echo ""
}

do_uninstall() {
    print_banner "PORTtralica Lumiya v0.6.073.8820 (Pilot) - UNINSTALLER"
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
    rm -rf "${TMPDIR:-/tmp}/lumiya_ipc_"* "/dev/shm/lumiya_ipc_"* "${XDG_CACHE_HOME:-$HOME/.cache}/lumiya_tmp/"* 2>/dev/null || true
    select_env_python
    if [ -n "$SELECTED_PY" ]; then
        "$SELECTED_PY" -m pip cache purge >/dev/null 2>&1 || true
    fi
    echo -e "  [${GREEN}DONE${RESET}] Workspace storage cleaned."
    exit 0
}

do_integrity() {
    print_banner
    echo -e "  [${CYAN}INTEGRITY${RESET}] Verifying SHA-256 and MD5 checksums against core/integrity.lmy..."
    select_env_python
    if [ -z "$SELECTED_PY" ]; then
        echo -e "  [${RED}ERROR${RESET}] No Python environment detected."
        exit 1
    fi
    "$SELECTED_PY" -c "
import sys
from pathlib import Path
from core.updater import computeProgramIntegrity
rep = computeProgramIntegrity(Path('.').resolve())
for k in ('master', 'core', 'scripts'):
    g = rep['lumpSums'][k]
    print(f\"  [{g['status']}]  {g['key']:<16} ({g['count']} files)  SHA-256: {g['sha256'][:16]}...  MD5: {g['md5']}\")
if rep['ok']:
    print('  \033[92m✔ You\x27re good! All tracked files match core/integrity.lmy.\033[0m')
else:
    print('  \033[91m✘ Integrity mismatch in:', ', '.join(rep['mismatches']), '\033[0m')
    sys.exit(1)
"
    exit $?
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
    SMI_BIN="$(find_nvidia_smi || true)"
    if [ -n "$SMI_BIN" ]; then
        echo -e "  GPU          : $("$SMI_BIN" --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -n 1)"
        echo -e "  Driver/CUDA  : $("$SMI_BIN" 2>/dev/null | grep -o 'CUDA Version: [0-9.]*' || true)"
    else
        echo -e "  GPU          : No NVIDIA GPU detected"
    fi
    select_env_python
    echo -e "  Python       : $SELECTED_PY ($("$SELECTED_PY" --version 2>/dev/null || echo 'Unknown'))"
    echo -e "  Temp Dir     : ${TMPDIR:-/tmp} ($TMPDIR_REASON)"
    if [ -f "$MANIFEST" ]; then
        echo ""
        echo "  --- Last Installation Manifest ---"
        tail -n 12 "$MANIFEST"
    fi
    exit 0
}

do_doctor() {
    print_banner
    echo -e "  [${CYAN}DOCTOR${RESET}] Deep Cross-Distro & Cluster Diagnostic:"
    check_distro
    echo -e "  Temp Dir     : ${TMPDIR:-/tmp} (${TMPDIR_REASON})"
    echo -e "  /tmp Free    : $(df -Ph /tmp 2>/dev/null | awk 'NR==2 {print $4 " free of " $2 " (" $1 ")"}' || echo 'Unknown')"
    if [ -d /dev/shm ]; then
        echo -e "  /dev/shm     : $(df -Ph /dev/shm 2>/dev/null | awk 'NR==2 {print $4 " free of " $2}' || echo 'Available')"
    fi
    if command -v quota >/dev/null 2>&1; then
        echo -e "  Disk Quotas  :"
        quota -w 2>/dev/null | sed 's/^/    /' || true
    fi
    select_env_python
    if [ -n "$SELECTED_PY" ]; then
        "$SELECTED_PY" protect.py --doctor
    else
        echo -e "  [${YELLOW}WARN${RESET}] No Python interpreter found."
    fi
    exit 0
}

do_reinstall_torch() {
    print_banner
    check_distro
    select_env_python
    TARGET_WHEEL="${1:-}"
    if [ -z "$TARGET_WHEEL" ]; then
        SMI_BIN="$(find_nvidia_smi || true)"
        CUDA_LEVEL=0
        if [ -n "$SMI_BIN" ]; then
            CUDA_VER_STR="$("$SMI_BIN" 2>/dev/null | grep -oE 'CUDA Version:[[:space:]]*[0-9]+\.[0-9]+' | grep -oE '[0-9]+\.[0-9]+' | head -n 1 || true)"
            if [ -n "$CUDA_VER_STR" ]; then
                MAJOR="$(echo "$CUDA_VER_STR" | cut -d'.' -f1 | tr -cd '0-9')"
                MINOR="$(echo "$CUDA_VER_STR" | cut -d'.' -f2 | tr -cd '0-9')"
                CUDA_LEVEL=$(( ${MAJOR:-12} * 10 + ${MINOR:-4} ))
            else
                CUDA_LEVEL=126
            fi
        fi
        TARGET_WHEEL="cu126"
        for ver in 132 130 128 126 124 121 118; do
            if [ "$CUDA_LEVEL" -ge "$ver" ]; then
                if "$SELECTED_PY" -m pip install --upgrade --force-reinstall --no-cache-dir torch torchvision --index-url "https://download.pytorch.org/whl/cu$ver"; then
                    TARGET_WHEEL="cu$ver"
                    break
                else
                    echo -e "  [${DIM}SKIP${RESET}]     Wheel index cu$ver not published yet; stepping down..."
                fi
            fi
        done
    else
        echo -e "  [${CYAN}CUDA${RESET}] Reinstalling hardware-matched PyTorch ($TARGET_WHEEL) into $SELECTED_ENV..."
        if [ "$TARGET_WHEEL" = "cpu" ]; then
            "$SELECTED_PY" -m pip install --upgrade --force-reinstall --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
        else
            "$SELECTED_PY" -m pip install --upgrade --force-reinstall --no-cache-dir torch torchvision --index-url "https://download.pytorch.org/whl/$TARGET_WHEEL"
        fi
    fi
    if "$SELECTED_PY" -c "import torch; raise SystemExit(0 if (torch.cuda.is_available() or getattr(torch.version, 'cuda', None) is not None) else 1)" 2>/dev/null; then
        echo -e "  [${GREEN}VERIFIED${RESET}] PyTorch $TARGET_WHEEL initialized CUDA successfully!"
    else
        echo -e "  [${YELLOW}WARNING${RESET}] PyTorch $TARGET_WHEEL installed. Note: torch.cuda.is_available() returned False."
    fi
    exit 0
}

# Pre-scan global environment flags (--tmp-dir, --cache-dir, --gpu, --cluster)
 PREV_ARG=""
for arg in "$@"; do
    case "$PREV_ARG" in
        --tmp-dir)
            export LUMIYA_TMP_DIR="$arg"
            ensure_smart_tmpdir 0
            PREV_ARG=""
            continue
            ;;
        --cache-dir)
            mkdir -p "$arg"
            export TORCH_HOME="$arg/torch"
            export HF_HOME="$arg/huggingface"
            export PIP_CACHE_DIR="$arg/pip"
            PREV_ARG=""
            continue
            ;;
        --gpu)
            export CUDA_VISIBLE_DEVICES="$arg"
            PREV_ARG=""
            continue
            ;;
    esac
    case "$arg" in
        --tmp-dir|--cache-dir|--gpu)
            PREV_ARG="$arg"
            ;;
        --cluster)
            ensure_smart_tmpdir 1
            ;;
    esac
done

# Omnipotent CLI argument & subcommand handling
case "${1:-}" in
    install|--install|-i|setup)
        shift
        do_install "$@"
        exit 0
        ;;
    reinstall-torch|fix-cuda|--reinstall-torch)
        shift
        do_reinstall_torch "$@"
        exit 0
        ;;
    uninstall|--uninstall|-u|remove)
        shift
        do_uninstall "$@"
        exit 0
        ;;
    purge|--purge)
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
    doctor|--doctor)
        shift
        do_doctor "$@"
        exit 0
        ;;
    integrity|--integrity|verify|--verify)
        shift
        do_integrity "$@"
        exit 0
        ;;
    cluster)
        shift
        ensure_smart_tmpdir 1
        set -- --cluster "$@"
        ;;
    update|--update)
        shift
        print_banner
        select_env_python
        if [ -z "$SELECTED_PY" ]; then
            echo -e "  [${RED}FATAL${RESET}] No usable Python interpreter available."
            exit 1
        fi
        LUMIYA_BANNER_PRINTED=1 exec "$SELECTED_PY" protect.py --update "$@"
        ;;
    headless)
        shift
        set -- --headless "$@"
        ;;
    free-port|--free-port|kill-port|--kill-port)
        PORT_TO_FREE="${2:-7860}"
        echo -e "  [${CYAN}PORT${RESET}] Releasing port ${PORT_TO_FREE} and terminating zombie processes..."
        if command -v fuser >/dev/null 2>&1; then
            fuser -k "${PORT_TO_FREE}/tcp" 2>/dev/null || true
        fi
        if command -v lsof >/dev/null 2>&1; then
            lsof -t -i:"${PORT_TO_FREE}" 2>/dev/null | xargs -r kill -9 2>/dev/null || true
        fi
        pkill -f "protect\.py.*--port ${PORT_TO_FREE}" 2>/dev/null || true
        echo -e "  [${GREEN}CLEARED${RESET}] Port ${PORT_TO_FREE} released."
        exit 0
        ;;
    port|--port|-p)
        shift
        WANTED_PORT="$1"
        shift
        set -- --port "$WANTED_PORT" "$@"
        ;;
    [0-9]*)
        WANTED_PORT="$1"
        shift
        set -- --port "$WANTED_PORT" "$@"
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
        echo "  update                Protected GitHub self-pull & dependency/integrity check"
        echo "  integrity, verify     Verify SHA-256 and MD5 checksums against core/integrity.lmy"
        echo "  reinstall-torch [cu]  Reinstall CUDA PyTorch into active environment (auto-detects driver CUDA)"
        echo "  uninstall, remove     Remove this program footprint dependencies (default: manifest cleanup)"
        echo "  purge                 Thoroughly purge runtime pillars"
        echo "  free-port [port]      Kill process occupying port (default: 7860)"
        echo "  clean                 Purge cache and temporary workspace files"
        echo "  test                  Run the core offline test suite"
        echo "  status                Display hardware, driver, and environment audit"
        echo "  doctor                Run deep cross-distro CUDA, NVML, font, and /tmp quota diagnostics"
        echo "  cluster               Launch in shared cluster/HPC mode (--no-browser, smart TMPDIR, /dev/shm IPC)"
        echo "  headless              Run batch protection directly from CLI without WebUI"
        echo "  start, run            Launch the Lumiya WebUI backend server"
        echo ""
        echo "Options:"
        echo "  -p, --port [port]     Bind WebUI to specific port (e.g. -p 7860 or ./run.sh 7860)"
        echo "  --host [host]         Bind to interface (default: 127.0.0.1, use 0.0.0.0 for LAN/remote)"
        echo "  --listen              Bind to 0.0.0.0 (allow remote, SSH tunnel, or cluster access)"
        echo "  --auth-token [token]  Require access token for WebUI API requests"
        echo "  --no-browser          Do not automatically launch system browser (recommended for remote/SSH)"
        echo "  --cluster             Cluster/HPC preset (--no-browser, smart TMPDIR, /dev/shm IPC)"
        echo "  --tmp-dir [dir]       Override temporary directory (TMPDIR)"
        echo "  --cache-dir [dir]     Override PyTorch/HuggingFace/pip cache directory"
        echo "  --results-dir [dir]   Override exported results directory"
        echo "  --device [dev]        Force compute backend (auto, cuda, cpu)"
        echo "  --gpu [id]            Select GPU index (sets CUDA_VISIBLE_DEVICES)"
        echo "  --tile-size [px]      Override spatial PGD tile size (256-1024)"
        echo "  --low-vram            Enable low-VRAM optimizations (512px tiles, fp16, RAM spillover)"
        echo "  --headless -i [path]  Run CLI batch immunization on file/folder (with -o, --algo, --steps, --budget)"
        echo "  --debug               Launch backend in emulation / verbose mode"
        echo "  -h, --help            Show this help reference"
        echo ""
        echo "All other arguments are passed directly to protect.py."
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

CONDA_CHECK_BIN="$(find_conda || true)"
if [ -n "$CONDA_CHECK_BIN" ]; then
    CONDA_CHECK_ROOT="$("$CONDA_CHECK_BIN" info --base 2>/dev/null || dirname "$(dirname "$CONDA_CHECK_BIN")")"
    echo -e "  [${GREEN}FOUND${RESET}]     Conda Root             : \"$CONDA_CHECK_ROOT\""
else
    echo -e "  [${YELLOW}MISSING${RESET}]   Conda Root             : Miniconda3 not detected (will auto-install on setup)"
fi

GPU_INFO="CPU Only (No NVIDIA GPU detected)"
SMI_BIN="$(find_nvidia_smi || true)"
if [ -n "$SMI_BIN" ]; then
    GPU_NAME="$("$SMI_BIN" --query-gpu=name --format=csv,noheader 2>/dev/null | head -n 1 || true)"
    CUDA_V="$("$SMI_BIN" 2>/dev/null | grep -oE 'CUDA Version:[[:space:]]*[0-9]+\.[0-9]+' | grep -oE '[0-9]+\.[0-9]+' | head -n 1 || true)"
    if [ -n "$GPU_NAME" ]; then
        GPU_INFO="$GPU_NAME (CUDA $CUDA_V)"
    fi
fi
echo -e "  [${CYAN}TARGET${RESET}]    Hardware / CUDA        : $GPU_INFO"

select_env_python

# If Conda 'lumiya' environment is not initialized, prompt
if [ -z "$SELECTED_PY" ]; then
    echo -e "  [${YELLOW}MISSING${RESET}]   Conda Environment      : Conda 'lumiya' environment not initialized"
    echo ""
    echo "  ===================================================================================================="
    echo -e "  ${YELLOW}[ENVIRONMENT NOT INITIALIZED]${RESET}"
    echo "    [I] Run environment installer now (auto-installs Miniconda3 if missing + CUDA PyTorch)"
    echo "    [W] Launch WebUI in limited mode (using Conda base Python)"
    echo "    [Q] Exit"
    echo "  ===================================================================================================="
    read -r -p "  Select option [I / W / Q]: " opt
    case "$opt" in
        [iI])
            do_install
            select_env_python
            ;;
        [wW])
            if [ -z "$CONDA_CHECK_BIN" ]; then
                bootstrap_miniconda
                CONDA_CHECK_BIN="$(find_conda || true)"
            fi
            if [ -n "$CONDA_CHECK_BIN" ]; then
                CONDA_CHECK_ROOT="$("$CONDA_CHECK_BIN" info --base 2>/dev/null || dirname "$(dirname "$CONDA_CHECK_BIN")")"
                SELECTED_PY="$CONDA_CHECK_ROOT/bin/python"
                SELECTED_ENV="base (\"$SELECTED_PY\")"
            fi
            ;;
        *)
            exit 0
            ;;
    esac
fi

if [ -z "$SELECTED_PY" ]; then
    log_err "FATAL: No usable Python interpreter available."
    echo -e "  [${RED}FATAL${RESET}] No usable Python interpreter available. Details logged to user/error.log"
    exit 1
fi

echo -e "  [${GREEN}ACTIVE${RESET}]    Environment            : $SELECTED_ENV"
"$SELECTED_PY" -c "import sys, torch; print(f'  [\x1b[96mRUNTIME\x1b[0m]   PyTorch / Python       : torch {torch.__version__} (CUDA={torch.cuda.is_available()}, build={getattr(torch.version, \"cuda\", None)}) // Python {sys.version.split()[0]}')" 2>/dev/null || true
echo -e "  [${DIM}LOGFILE${RESET}]   Diagnostic Error Log   : \"$ERRLOG\""
echo "  ===================================================================================================="

export LUMIYA_BANNER_PRINTED=1
set +e
"$SELECTED_PY" protect.py "$@"
EXIT_CODE=$?
if [ "$EXIT_CODE" -ne 0 ]; then
    log_err "protect.py exited with non-zero code $EXIT_CODE."
    echo -e "  [${RED}ERROR${RESET}]     Service exited with code $EXIT_CODE. Diagnostic details written to user/error.log"
    exit "$EXIT_CODE"
fi
