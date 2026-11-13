from __future__ import annotations

import argparse
import base64
import copy
import importlib.metadata
import importlib.util
import io
import json
import math
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
import uuid
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.cleaner import cleanMemoryAndStorage
from core.init import (
    APP_NAME,
    APP_VERSION,
    VALID_EXTS,
    AlgoPluginManager,
    SuiteConfig,
    TelemetryMonitor,
    clampSetting,
    computeProgramIntegrity,
    runProtectedUpdate,
    safeInt,
    sanitizeFilename,
    verifyBrandAssets,
)
from core.queue import QueueManager, RuntimeState
from core.server import ServerApp, findAvailablePort, serve
from core.termlog import TermLog
from stego.mark import embedMark

# The progress bar uses block characters a legacy console codepage cannot encode.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore", message=".*pynvml.*deprecated.*", category=UserWarning)


def _installGlobalExceptionHook() -> None:
    origHook = sys.excepthook

    def _lumiyaExceptHook(excType: Any, excValue: Any, excTb: Any) -> None:
        if issubclass(excType, KeyboardInterrupt):
            origHook(excType, excValue, excTb)
            return
        import traceback
        tbText = "".join(traceback.format_exception(excType, excValue, excTb))
        TermLog.writeErrorLog(f"Uncaught {getattr(excType, '__name__', 'Exception')}", tbText, module="protect.py")
        origHook(excType, excValue, excTb)

    sys.excepthook = _lumiyaExceptHook


_installGlobalExceptionHook()


DEPS_STATUS: Dict[str, Any] = {
    "torch": False,
    "cuda": False,
    "diffusers": False,
    "transformers": False,
    "pil": False,
    "psutil": False,
    "git": shutil.which("git") is not None or Path(r"C:\Program Files\Git\cmd\git.exe").exists(),
    "conda": (
        shutil.which("conda") is not None
        or Path(os.path.expanduser("~/miniconda3")).exists()
        or Path(os.path.expanduser("~/anaconda3")).exists()
    ),
    "versions": {
        "python": sys.version.split()[0],
        "torch": "Not Installed",
        "cuda": "Not Available",
        "diffusers": "Not Installed",
        "transformers": "Not Installed",
        "pil": "Not Installed",
        "psutil": "Not Installed",
        "git": "Detected" if (shutil.which("git") or Path(r"C:\Program Files\Git\cmd\git.exe").exists()) else "Missing",
        "conda": "Detected"
        if (shutil.which("conda") or Path(os.path.expanduser("~/miniconda3")).exists() or Path(os.path.expanduser("~/anaconda3")).exists())
        else "Missing",
    },
    # Package rows are filled from the pins in core/requirements.txt once REQ_FILE is known.
    "recommended": {
        "python": "3.12.x - 3.13.x",
        "cuda": "Matched to driver",
        "git": ">= 2.45.0",
        "conda": "Miniconda3 24.x+",
    },
    "gpuName": "CPU",
    "vramGb": 0.0,
    "hardwareAdvisory": False,
    "advisoryReason": "",
}


def resolveNvidiaSmi() -> str:
    found = shutil.which("nvidia-smi")
    if found:
        return found
    candidates = (
        (
            r"C:\Windows\System32\nvidia-smi.exe",
            r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
        )
        if sys.platform == "win32"
        else (
            "/usr/bin/nvidia-smi",
            "/usr/local/cuda/bin/nvidia-smi",
            "/opt/cuda/bin/nvidia-smi",
        )
    )
    for p in candidates:
        if Path(p).exists():
            return p
    return "nvidia-smi"


def _applyEarlyCliEnv() -> None:
    """Applies --gpu, --tmp-dir, --cache-dir, and --cluster environment variables before CUDA/PyTorch probing."""
    argv = sys.argv[1:]
    for i, arg in enumerate(argv):
        if arg == "--gpu" and i + 1 < len(argv):
            os.environ["CUDA_VISIBLE_DEVICES"] = argv[i + 1]
        elif arg == "--tmp-dir" and i + 1 < len(argv):
            tmpPath = Path(argv[i + 1]).resolve()
            tmpPath.mkdir(parents=True, exist_ok=True)
            os.environ["TMPDIR"] = str(tmpPath)
            os.environ["TEMP"] = str(tmpPath)
            os.environ["TMP"] = str(tmpPath)
        elif arg == "--cache-dir" and i + 1 < len(argv):
            cachePath = Path(argv[i + 1]).resolve()
            cachePath.mkdir(parents=True, exist_ok=True)
            os.environ["TORCH_HOME"] = str(cachePath / "torch")
            os.environ["HF_HOME"] = str(cachePath / "huggingface")
            os.environ["PIP_CACHE_DIR"] = str(cachePath / "pip")
        elif arg == "--cluster" and sys.platform != "win32" and "TMPDIR" not in os.environ:
            try:
                if shutil.disk_usage("/tmp").free < 4 * (1024 ** 3):
                    fallbackTmp = Path.home() / ".cache" / "lumiya_tmp"
                    fallbackTmp.mkdir(parents=True, exist_ok=True)
                    os.environ["TMPDIR"] = str(fallbackTmp)
            except Exception:
                pass


def ensureLinuxCudaLibPath() -> None:
    if sys.platform != "win32":
        for p in (
            "/usr/lib/x86_64-linux-gnu",
            "/usr/lib64",
            "/usr/lib64/nvidia",
            "/usr/lib",
            "/opt/cuda/lib64",
            "/usr/local/cuda/lib64",
            "/usr/local/cuda/targets/x86_64-linux/lib",
            "/run/opengl-driver/lib",
            "/usr/lib/wsl/lib",
        ):
            if os.path.isdir(p):
                cur = os.environ.get("LD_LIBRARY_PATH", "")
                if p not in cur.split(":"):
                    os.environ["LD_LIBRARY_PATH"] = f"{cur}:{p}" if cur else p


_applyEarlyCliEnv()
ensureLinuxCudaLibPath()

NVIDIA_SMI_BIN = resolveNvidiaSmi()


def probePkgVersion(pkgName: str, modName: str) -> Optional[str]:
    try:
        return importlib.metadata.version(pkgName)
    except Exception:
        try:
            return "Verified" if importlib.util.find_spec(modName) is not None else None
        except Exception:
            return None


def probeStartupDeps() -> None:
    """Probes installed packages and GPU metadata without importing heavy ML runtimes at startup."""
    global psutil, Image, ImageOps, PngImagePlugin
    try:
        import psutil as _psutil
        psutil = _psutil
        DEPS_STATUS["psutil"] = True
        DEPS_STATUS["versions"]["psutil"] = getattr(_psutil, "__version__", "Verified")
    except Exception:
        psutil = None

    try:
        from PIL import Image as _Image, ImageOps as _ImageOps, PngImagePlugin as _PngImagePlugin
        import PIL as _PIL
        Image, ImageOps, PngImagePlugin = _Image, _ImageOps, _PngImagePlugin
        DEPS_STATUS["pil"] = True
        DEPS_STATUS["versions"]["pil"] = getattr(_PIL, "__version__", "Verified")
    except Exception:
        Image = ImageOps = PngImagePlugin = None

    for key, pkg, mod in (
        ("torch", "torch", "torch"),
        ("diffusers", "diffusers", "diffusers"),
        ("transformers", "transformers", "transformers"),
    ):
        ver = probePkgVersion(pkg, mod)
        if ver:
            DEPS_STATUS[key] = True
            DEPS_STATUS["versions"][key] = ver

    if DEPS_STATUS["torch"] and "--compute-worker" in sys.argv:
        try:
            import torch as _t
            if _t.cuda.is_available():
                DEPS_STATUS["cuda"] = True
                DEPS_STATUS["versions"]["cuda"] = str(_t.version.cuda or "Unknown")
                DEPS_STATUS["gpuName"] = _t.cuda.get_device_name(0)
                DEPS_STATUS["vramGb"] = round(_t.cuda.get_device_properties(0).total_memory / (1024 ** 3), 2)
            else:
                DEPS_STATUS["cuda"] = False
                DEPS_STATUS["versions"]["cuda"] = "Not Available"
        except Exception:
            DEPS_STATUS["cuda"] = False
            DEPS_STATUS["versions"]["cuda"] = "Not Available"
    elif DEPS_STATUS["torch"]:
        cudaProbeOk = False
        probeErr = ""
        probeInfo = {}
        tVer = str(DEPS_STATUS["versions"]["torch"])

        # 1. Quick probe to test real PyTorch CUDA availability in an isolated subprocess
        probeScript = (
            "import json, sys\n"
            "try:\n"
            "    import torch\n"
            "    ok = bool(torch.cuda.is_available())\n"
            "    ver = str(getattr(torch.version, 'cuda', None) or 'Unknown')\n"
            "    name = torch.cuda.get_device_name(0) if ok else 'CPU'\n"
            "    vram = round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 2) if ok else 0.0\n"
            "    print(json.dumps({'cuda': ok, 'ver': ver, 'name': name, 'vram': vram, 'err': ''}))\n"
            "except Exception as e:\n"
            "    print(json.dumps({'cuda': False, 'ver': '', 'name': '', 'vram': 0.0, 'err': str(e)}))\n"
        )
        try:
            startupInfo = None
            if sys.platform == "win32":
                startupInfo = subprocess.STARTUPINFO()
                startupInfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            probeJson = subprocess.check_output(
                [sys.executable, "-c", probeScript],
                startupinfo=startupInfo,
                stderr=subprocess.DEVNULL,
                # Generous: a cold torch import on Windows can take well over 12 s, and a timeout here means "no CUDA" for the session.
                timeout=60.0,
            ).decode("utf-8", errors="replace").strip()
            probeInfo = json.loads(probeJson.splitlines()[-1])
            cudaProbeOk = bool(probeInfo.get("cuda"))
            probeErr = str(probeInfo.get("err") or "")
        except Exception as exc:
            probeErr = str(exc)

        # 2. Inspect physical GPU hardware via nvidia-smi
        smiGpuName = ""
        smiMemMb = 0.0
        try:
            startupInfo = None
            if sys.platform == "win32":
                startupInfo = subprocess.STARTUPINFO()
                startupInfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            out = subprocess.check_output(
                [NVIDIA_SMI_BIN, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                startupinfo=startupInfo,
                stderr=subprocess.DEVNULL,
                timeout=5.0,
            ).decode("utf-8", errors="replace").strip()
            firstLine = out.splitlines()[0]
            smiGpuName, memStr = [x.strip() for x in firstLine.split(",", 1)]
            smiMemMb = float(memStr.split()[0])
        except Exception:
            pass

        if cudaProbeOk:
            DEPS_STATUS["cuda"] = True
            DEPS_STATUS["versions"]["cuda"] = probeInfo.get("ver", "Working")
            DEPS_STATUS["gpuName"] = probeInfo.get("name") or smiGpuName or "NVIDIA GPU"
            DEPS_STATUS["vramGb"] = float(probeInfo.get("vram") or (smiMemMb / 1024.0 if smiMemMb else 8.0))
        elif smiGpuName:
            DEPS_STATUS["cuda"] = False
            DEPS_STATUS["gpuName"] = smiGpuName
            DEPS_STATUS["vramGb"] = round(smiMemMb / 1024.0, 2) if smiMemMb else 0.0
            DEPS_STATUS["hardwareAdvisory"] = True
            if "+cpu" in tVer.lower():
                DEPS_STATUS["versions"]["cuda"] = "Not Available (CPU Build)"
                DEPS_STATUS["advisoryReason"] = f"NVIDIA GPU ({smiGpuName}) detected, but PyTorch is installed with CPU build ({tVer}). Run install.bat or ./run.sh install to install hardware-matched CUDA PyTorch."
            else:
                DEPS_STATUS["versions"]["cuda"] = "Not Available (Driver Mismatch)"
                DEPS_STATUS["advisoryReason"] = f"PyTorch {tVer} CUDA initialization failed ({probeErr or 'driver mismatch'}). Run install.bat or ./run.sh install to select a driver-compatible CUDA wheel."
        else:
            DEPS_STATUS["cuda"] = False
            DEPS_STATUS["hardwareAdvisory"] = True
            DEPS_STATUS["versions"]["cuda"] = "Not Available"
            if not DEPS_STATUS["advisoryReason"]:
                DEPS_STATUS["advisoryReason"] = (
                    "No CUDA-accelerable hardware detected. Running this program on non-CUDA accelerated platform "
                    "will be considerably slower. Consider changing the platform or continue and accept less optimal performance."
                )
    else:
        DEPS_STATUS["hardwareAdvisory"] = True
        DEPS_STATUS["advisoryReason"] = "PyTorch CUDA runtime is not installed."


psutil: Any = None
Image: Any = None
ImageOps: Any = None
PngImagePlugin: Any = None
torch: Any = None
F: Any = None
T: Any = None
AutoencoderKL: Any = None
probeStartupDeps()


ROOT_DIR = Path(__file__).resolve().parent
ALGOS_DIR = ROOT_DIR / "algos"
RESULTS_ROOT = ROOT_DIR / "results"
IDENTITY_DIR = ROOT_DIR / "identity"
THEMES_DIR = IDENTITY_DIR / "theme"
USER_DIR = ROOT_DIR / "user"


UI_FILE = (ROOT_DIR / "core" / "ui.html") if (ROOT_DIR / "core" / "ui.html").exists() else (ROOT_DIR / "ui.html")
REQ_FILE = (ROOT_DIR / "core" / "requirements.txt") if (ROOT_DIR / "core" / "requirements.txt").exists() else (ROOT_DIR / "requirements.txt")
CONFIG_FILE = USER_DIR / "config.json"
_REQ_KEYS = {"torch": "torch", "diffusers": "diffusers", "transformers": "transformers", "pillow": "pil", "psutil": "psutil"}
for _pin in REQ_FILE.read_text(encoding="utf-8").splitlines() if REQ_FILE.is_file() else []:
    _name, _, _ver = (part.strip() for part in _pin.partition("=="))
    if _name.lower() in _REQ_KEYS and _ver:
        DEPS_STATUS["recommended"][_REQ_KEYS[_name.lower()]] = _ver + (" (build matched to driver)" if _name.lower() == "torch" else "")
HISTORY_FILE = USER_DIR / "history.json"
MANIFEST_FILE = USER_DIR / "install_manifest.log"

BRAND_STATUS = verifyBrandAssets(ROOT_DIR)
CFG = SuiteConfig.load(CONFIG_FILE)


def nativeTiles(width: int, height: int, workingDim: int = 768, allowRamSpillover: bool = True, vramGb: float = 6.0) -> List[Tuple[int, int, int, int]]:
    """Builds 1:1 native-resolution tile coordinates (y0, y1, x0, x1) with dimensions divisible by 8 so PGD never blurs gradients via downsampling."""
    maxDim = max(512, int(workingDim or 768))
    if allowRamSpillover or vramGb >= 8.0:
        maxDim = max(maxDim, 1024)
    tileH = max(8, min((height // 8) * 8, (maxDim // 8) * 8))
    tileW = max(8, min((width // 8) * 8, (maxDim // 8) * 8))

    def axisStops(total: int, span: int) -> List[int]:
        if total <= span:
            return [0]
        stride = max(8, int(span * 0.85))
        stops = list(range(0, total - span, stride))
        if not stops or stops[-1] != total - span:
            stops.append(total - span)
        return stops

    ys = axisStops(height, tileH)
    xs = axisStops(width, tileW)
    return [(y0, y0 + tileH, x0, x0 + tileW) for y0 in ys for x0 in xs]


class ModularDefenseEngine:
    def __init__(self, algoMgr: AlgoPluginManager, useSubprocess: bool = True) -> None:
        self.algoMgr = algoMgr
        self.useSubprocess = useSubprocess
        self.computeProc: Optional[subprocess.Popen] = None
        self.vae: Optional[Any] = None
        self.vaeDevice: Optional[str] = None
        self.cache: Dict[Tuple[int, int, str, str], Any] = {}

    @property
    def majorDepsReady(self) -> bool:
        return bool(DEPS_STATUS["torch"] and DEPS_STATUS["diffusers"] and DEPS_STATUS["pil"])

    def resolveDevice(self) -> str:
        if CFG.computeBackend in ("auto", "cuda", "opengl") and DEPS_STATUS["cuda"]:
            return "cuda"
        return "cpu"

    @staticmethod
    def validateTensorShape(tensor: Any, expectedNdim: int = 4, name: str = "tensor") -> None:
        if tensor.ndim != expectedNdim:
            raise ValueError(f"Expected {expectedNdim}D {name}, got shape {tuple(tensor.shape)}")
        if not torch.isfinite(tensor).all():
            raise RuntimeError(f"Non-finite values (NaN/Inf) detected in {name}")

    def ensureLoaded(self) -> Tuple[str, Any]:
        global torch, F, T, AutoencoderKL
        if not self.majorDepsReady:
            raise RuntimeError("Missing required dependencies. Open Configuration tab to install.")
        if torch is None or F is None or T is None or AutoencoderKL is None:
            import torch as _torch
            import torch.nn.functional as _F
            import torchvision.transforms as _T
            from diffusers import AutoencoderKL as _AutoencoderKL
            torch, F, T, AutoencoderKL = _torch, _F, _T, _AutoencoderKL
            DEPS_STATUS["cuda"] = bool(torch.cuda.is_available())
            if DEPS_STATUS["cuda"]:
                DEPS_STATUS["gpuName"] = torch.cuda.get_device_name(0)
                DEPS_STATUS["vramGb"] = round(torch.cuda.get_device_properties(0).total_memory / (1024 ** 3), 2)

        device = self.resolveDevice()
        dtype = torch.float16 if (device == "cuda" and CFG.precision == "fp16") else torch.float32

        if self.vae is None:
            t0 = time.time()
            TermLog.emit(f"Loading AutoencoderKL onto {TermLog.CYAN}{device.upper()}{TermLog.RESET} ({dtype})", "engine.py", "INFO")
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    self.vae = AutoencoderKL.from_pretrained(
                        "stabilityai/sd-vae-ft-mse", torch_dtype=dtype, local_files_only=True
                    ).to(device)
                except Exception:
                    self.vae = AutoencoderKL.from_pretrained(
                        "stabilityai/sd-vae-ft-mse", torch_dtype=dtype
                    ).to(device)
            if hasattr(self.vae, "enable_slicing"):
                self.vae.enable_slicing()
            self.vae.eval()
            for param in self.vae.parameters():
                param.requires_grad = False
            self.vaeDevice = device
            TermLog.emit(f"Model ready in {TermLog.CYAN}{time.time() - t0:.2f}{TermLog.RESET}s", "engine.py", "OK")
        elif self.vaeDevice != device or next(self.vae.parameters()).dtype != dtype:
            self.vae = self.vae.to(device=device, dtype=dtype)
            self.vaeDevice = device

        return device, dtype

    def unloadModel(self) -> bool:
        """Terminates the isolated CUDA compute worker subprocess and releases any in-process caches to drop idle RAM/VRAM to baseline."""
        hadModel = self.vae is not None or bool(self.cache) or (self.computeProc is not None)
        if getattr(self, "workerErrFile", None) and not self.workerErrFile.closed:
            try:
                self.workerErrFile.close()
            except Exception:
                pass
            self.workerErrFile = None
        if self.computeProc is not None:
            proc = self.computeProc
            self.computeProc = None
            try:
                if proc.stdin:
                    proc.stdin.close()
            except Exception:
                pass
            try:
                proc.kill()
                proc.wait(timeout=3.0)
            except Exception:
                pass
        if self.vae is not None:
            try:
                self.vae.to("cpu")
            except Exception:
                pass
        self.vae = None
        self.vaeDevice = None
        self.cache.clear()
        if self.algoMgr is not None and hasattr(self.algoMgr, "plugins"):
            for p in self.algoMgr.plugins.values():
                p["module"] = None
        return hadModel

    @staticmethod
    def visibilityMap(xOrig: Any) -> Any:
        """Per-pixel share of the budget: full in detail/edges, near-zero in flat areas where eyes notice change."""
        luma = (xOrig * torch.tensor([0.299, 0.587, 0.114], device=xOrig.device).view(1, 3, 1, 1)).sum(1, keepdim=True)
        radius = max(3, min(xOrig.shape[-2:]) // 240)
        size = 2 * radius + 1
        mean = F.avg_pool2d(luma, size, 1, radius)
        spread = (F.avg_pool2d(luma ** 2, size, 1, radius) - mean ** 2).clamp(min=0.0).sqrt()
        return F.avg_pool2d((spread / 0.065).clamp(0.04, 1.0), size, 1, radius)

    def grayTarget(self, height: int, width: int, device: str, dtype: Any) -> Any:
        """VAE latent of a mid-gray image, the target of encoder-attack style plugins."""
        key = (height, width, device, str(dtype))
        if key not in self.cache:
            with torch.no_grad():
                gray = torch.zeros(1, 3, height, width, device=device, dtype=dtype)
                self.cache[key] = self.vae.encode(gray).latent_dist.mean.detach().float()
        return self.cache[key]

    def cleanLatentTile(self, xOrig: Any, y0: int, y1: int, x0: int, x1: int, device: str, dtype: Any) -> Tuple[Any, Any]:
        """Cached clean 1:1 native-resolution tile [-1, 1] and its VAE latent mean for divergence/relative losses."""
        xKey = (-1, y0, y1, x0, x1, device, "xOrigTile")
        zKey = (-1, y0, y1, x0, x1, device, str(dtype))
        if xKey not in self.cache or zKey not in self.cache:
            with torch.no_grad():
                xOrigWork = xOrig[:, :, y0:y1, x0:x1] * 2.0 - 1.0
                zOrigMean = self.vae.encode(xOrigWork.to(dtype)).latent_dist.mean.detach().float()
                self.cache[xKey] = xOrigWork
                self.cache[zKey] = zOrigMean
        return self.cache[xKey], self.cache[zKey]

    @staticmethod
    def encodeOutputImage(
        pilImg: Any,
        fileExt: str,
        hasStego: bool,
        stegoText: str,
        exifBytes: Any = None,
        iccProfile: Any = None,
        stegoOpts: Optional[Dict[str, Any]] = None,
        alpha: Any = None,
    ) -> bytes:
        opts = stegoOpts or {}
        ext = fileExt.lower()
        if hasStego:
            pilImg = embedMark(pilImg, stegoText, opts, lossless=ext not in (".jpg", ".jpeg"))
        if alpha is not None and ext in (".png", ".webp", ".tiff"):
            pilImg = pilImg.convert("RGBA")
            pilImg.putalpha(alpha)
        outBuf = io.BytesIO()
        saveKw: Dict[str, Any] = {}
        if iccProfile:
            saveKw["icc_profile"] = iccProfile
        if ext in (".jpg", ".jpeg"):
            if exifBytes:
                saveKw["exif"] = exifBytes
            if hasStego and stegoText.strip():
                saveKw["comment"] = f"[LUMIYA::{stegoText}]".encode("utf-8")
            try:
                pilImg.convert("RGB").save(outBuf, format="JPEG", quality=CFG.jpegQuality, subsampling=0, optimize=True, **saveKw)
            except Exception:
                saveKw.pop("exif", None)
                outBuf.seek(0)
                outBuf.truncate(0)
                pilImg.convert("RGB").save(outBuf, format="JPEG", quality=CFG.jpegQuality, subsampling=0, optimize=True, **saveKw)
            markBytes = opts.get("mark") if (hasStego and opts.get("payload") == "image") else None
            if markBytes:
                outBuf.write(base64.b64decode(markBytes))
        elif ext == ".png":
            if exifBytes:
                saveKw["exif"] = exifBytes
            if hasStego and stegoText.strip() and PngImagePlugin is not None:
                pInfo = PngImagePlugin.PngInfo()
                pInfo.add_text("LumiyaStego", f"[LUMIYA::{stegoText}]")
                saveKw["pnginfo"] = pInfo
            pilImg.save(outBuf, format="PNG", compress_level=3, **saveKw)
        elif ext == ".webp":
            if exifBytes:
                saveKw["exif"] = exifBytes
            pilImg.save(outBuf, format="WEBP", lossless=True, **saveKw)
        elif ext == ".tiff":
            pilImg.save(outBuf, format="TIFF", compression="tiff_lzw", **saveKw)
        else:
            pilImg.convert("RGB").save(outBuf, format="BMP")
        return outBuf.getvalue()

    @staticmethod
    def _computeMetrics(origArr: Any, outBytes: bytes) -> Tuple[float, float]:
        import numpy as np
        after = np.asarray(Image.open(io.BytesIO(outBytes)).convert("RGB"), dtype=np.float32)
        diff = after - origArr
        del after
        mse = float(np.mean(diff ** 2))
        psnr = 10.0 * math.log10((255.0 ** 2) / max(mse, 1e-10))
        shift = float(np.abs(diff).max())
        del diff
        return psnr, shift

    def processImage(
        self,
        rawBytes: bytes,
        fileExt: str,
        epsilon255: float,
        steps: int,
        stegoMode: str,
        stegoText: str,
        layers: Dict[str, bool],
        stepCb: Any,
        controlCb: Any,
        emulateDebug: bool = False,
        guidancePrompt: str = "",
        geoAnchorLow: float = 1.7,
        geoAnchorHigh: float = 7.1,
        temporalWeight: float = 0.50,
        maskAugFactor: float = 1.00,
        computeLevel: float = 1.0,
        seed: int = 0,
        stegoOpts: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bytes, int, int, float, float]:
        opts = stegoOpts or {}
        payloadType = str(opts.get("payload", "text"))
        hasStegoPayload = bool(stegoText.strip()) if payloadType in ("text", "binary") else bool(opts.get("mark"))

        if emulateDebug or stegoMode == "only":
            tStart = time.time()
            if emulateDebug and stegoMode != "only":
                # Debug emulation stands in for a real run, so it walks the step count; stego-only has no steps to show.
                for step in range(1, steps + 1):
                    if controlCb() == "STOP":
                        raise InterruptedError("Stopped")
                    time.sleep(0.05)
                    el = max(time.time() - tStart, 1e-4)
                    TermLog.progress(step, steps, el)
                    stepCb(step, steps, el)

            if DEPS_STATUS["pil"]:
                rawIm = Image.open(io.BytesIO(rawBytes))
                transposedIm = ImageOps.exif_transpose(rawIm)
                exifBytes = transposedIm.getexif().tobytes() if CFG.preserveExif and "exif" in rawIm.info else None
                iccProfile = rawIm.info.get("icc_profile") if CFG.preserveIcc else None
                im = transposedIm.convert("RGB")
                width, height = im.size
                hasStego = stegoMode in ("only", "combined") and hasStegoPayload
                alpha = transposedIm.getchannel("A") if "A" in transposedIm.getbands() else None
                outBytes = self.encodeOutputImage(im, fileExt, hasStego, stegoText, exifBytes, iccProfile, opts, alpha)
                if stegoMode == "only":
                    stepCb(1, 1, max(time.time() - tStart, 1e-4))
                import numpy as np
                before = np.asarray(im, dtype=np.float32)
                del im, transposedIm, rawIm
                psnr, shift = self._computeMetrics(before, outBytes)
                del before
                return outBytes, width, height, psnr, shift
            return rawBytes, 512, 512, 0.0, 0.0

        if self.useSubprocess:
            return self._processImageViaSubprocess(
                rawBytes=rawBytes,
                fileExt=fileExt,
                epsilon255=epsilon255,
                steps=steps,
                stegoMode=stegoMode,
                stegoText=stegoText,
                layers=layers,
                stepCb=stepCb,
                controlCb=controlCb,
                guidancePrompt=guidancePrompt,
                geoAnchorLow=geoAnchorLow,
                geoAnchorHigh=geoAnchorHigh,
                temporalWeight=temporalWeight,
                maskAugFactor=maskAugFactor,
                computeLevel=computeLevel,
                seed=seed,
                opts=opts,
            )

        device, dtype = self.ensureLoaded()

        rawIm = Image.open(io.BytesIO(rawBytes))
        transposedIm = ImageOps.exif_transpose(rawIm)
        exifBytes = transposedIm.getexif().tobytes() if CFG.preserveExif and "exif" in rawIm.info else None
        iccProfile = rawIm.info.get("icc_profile") if CFG.preserveIcc else None
        alpha = transposedIm.getchannel("A") if "A" in transposedIm.getbands() else None
        origRgb = transposedIm.convert("RGB")
        origW, origH = origRgb.size

        nowStamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        activePlugins = []
        for plugin in self.algoMgr.selectRunnable(layers):
            CFG.algoLastUsed[plugin["id"]] = nowStamp
            mod = self.algoMgr.getPluginModule(plugin["id"])
            if mod is not None:
                activePlugins.append((mod, plugin["paper"] or {"budget": epsilon255, "steps": steps}))
        if not activePlugins:
            raise RuntimeError("None of the selected algorithms can run on this system.")

        budget = float(epsilon255)
        eps = budget / 255.0

        gen = torch.Generator().manual_seed(int(seed))
        xOrig = T.ToTensor()(origRgb).unsqueeze(0).to(device, dtype=torch.float32)
        limitMap = eps * self.visibilityMap(xOrig)
        delta = torch.zeros_like(xOrig)
        allowSpill = bool(getattr(CFG, "allowRamSpillover", True))
        vramGb = float(DEPS_STATUS.get("vramGb", 0.0))
        tiles = nativeTiles(origW, origH, int(getattr(CFG, "workingDim", 768)), allowSpill, vramGb)
        ctx: Dict[str, Any] = {
            "guidancePrompt": guidancePrompt,
            "generator": gen,
            "origSize": (origH, origW),
            "budget": budget,
            "temporalWeight": temporalWeight,
            "maskAugFactor": maskAugFactor,
            "geoAnchorLow": geoAnchorLow,
            "geoAnchorHigh": geoAnchorHigh,
        }
        for k in [ck for ck in self.cache if isinstance(ck[0], int) and ck[0] < 0]:
            self.cache.pop(k, None)
        totalSteps = sum(max(1, round(int(paper.get("steps", steps)) * computeLevel)) for _, paper in activePlugins)
        tStart = time.time()
        step = appliedSteps = 0

        try:
            for mod, paper in activePlugins:
                pluginSteps = max(1, round(int(paper.get("steps", steps)) * computeLevel))
                visitsPerTile = max(1, math.ceil(pluginSteps / max(1, len(tiles))))
                stepRatio = 1.6 / visitsPerTile
                lossFn = getattr(mod, "computeLoss", None)
                if lossFn is None:
                    continue
                transformFn = getattr(mod, "transformInput", None)
                for _ in range(pluginSteps):
                    if controlCb() == "STOP":
                        raise InterruptedError("Batch stopped by user.")
                    step += 1
                    y0, y1, x0, x1 = tiles[(step - 1) % len(tiles)]
                    workH, workW = y1 - y0, x1 - x0
                    xOrigTile = xOrig[:, :, y0:y1, x0:x1]
                    limitTile = limitMap[:, :, y0:y1, x0:x1]
                    deltaTile = delta[:, :, y0:y1, x0:x1].detach().clone().requires_grad_(True)
                    xAdvTile = torch.clamp(xOrigTile + deltaTile, 0.0, 1.0)
                    if not torch.isfinite(xAdvTile).all():
                        with torch.no_grad():
                            delta[:, :, y0:y1, x0:x1].zero_()
                        deltaTile = torch.zeros_like(xOrigTile, requires_grad=True)
                        xAdvTile = xOrigTile.clone()

                    xWork = xAdvTile * 2.0 - 1.0
                    xOrigWork, zOrigMean = self.cleanLatentTile(xOrig, y0, y1, x0, x1, device, dtype)
                    ctx["zTargetMean"] = self.grayTarget(workH, workW, device, dtype)
                    ctx["zOrigMean"] = zOrigMean
                    ctx["xOrigWork"] = xOrigWork
                    ctx["xWork"] = xWork
                    ctx["step"] = step
                    ctx["totalSteps"] = pluginSteps

                    loss = gradTile = xIn = None
                    try:
                        xIn = transformFn(xWork, step, ctx) if transformFn else xWork
                        ctx["xIn"] = xIn
                        self.validateTensorShape(xIn, 4, "xIn")
                        loss = lossFn(self.vae.encode(xIn.to(dtype)).latent_dist, ctx)
                        gradTile = torch.autograd.grad(loss, deltaTile)[0] if torch.isfinite(loss) else None
                    except RuntimeError as oomExc:
                        if allowSpill and "out of memory" in str(oomExc).lower() and device == "cuda":
                            loss = gradTile = xIn = None
                            ctx.pop("xIn", None)
                            ctx.pop("vetoCurrentImage", None)
                            torch.cuda.empty_cache()
                            if hasattr(self.vae, "enable_tiling"):
                                self.vae.enable_tiling()
                            with torch.autograd.graph.save_on_cpu(pin_memory=False):
                                xIn = transformFn(xWork, step, ctx) if transformFn else xWork
                                ctx["xIn"] = xIn
                                loss = lossFn(self.vae.encode(xIn.to(dtype)).latent_dist, ctx)
                                gradTile = torch.autograd.grad(loss, deltaTile)[0] if torch.isfinite(loss) else None
                        else:
                            raise

                    if gradTile is not None and torch.isfinite(gradTile).all():
                        with torch.no_grad():
                            rms = gradTile.pow(2).mean().sqrt().clamp(min=1e-12)
                            stepUpdate = stepRatio * limitTile * (gradTile / rms).clamp(-2.0, 2.0)
                            nextDelta = torch.clamp(delta[:, :, y0:y1, x0:x1] - stepUpdate, -limitTile, limitTile)
                            delta[:, :, y0:y1, x0:x1] = torch.clamp(xOrigTile + nextDelta, 0.0, 1.0) - xOrigTile
                        appliedSteps += 1

                    # Release per-step autograd graph references immediately so two steps never coexist in RAM/VRAM
                    loss = gradTile = deltaTile = xAdvTile = xWork = xIn = None
                    ctx.pop("xWork", None)
                    ctx.pop("xIn", None)
                    ctx.pop("xOrigWork", None)
                    ctx.pop("vetoCurrentImage", None)

                    elapsed = max(time.time() - tStart, 1e-4)
                    TermLog.progress(step, totalSteps, elapsed)
                    stepCb(step, totalSteps, elapsed)

            if appliedSteps == 0:
                raise RuntimeError("No optimization step produced a valid finite loss; image was not protected.")

            import numpy as np
            limit = math.floor(budget)
            scaled = (delta.detach() * 255.0).squeeze(0).cpu()
            if not torch.isfinite(scaled).all():
                scaled = torch.zeros_like(scaled)
            deltaInt = torch.round(scaled).clamp(-limit, limit).to(torch.int16).permute(1, 2, 0).numpy()
            del scaled
        finally:
            ctx.clear()
            for k in [ck for ck in list(self.cache.keys()) if isinstance(ck[0], int) and ck[0] < 0]:
                self.cache.pop(k, None)
            del xOrig, limitMap, delta
            if device == "cuda" and torch is not None and torch.cuda.is_available():
                torch.cuda.empty_cache()
        origArr = np.asarray(origRgb, dtype=np.float32)
        del rawIm, transposedIm, origRgb
        outArr = np.clip(origArr + deltaInt, 0, 255).astype(np.uint8)
        outPil = Image.fromarray(outArr)
        del deltaInt, outArr
        hasStego = stegoMode == "combined" and hasStegoPayload
        outBytes = self.encodeOutputImage(outPil, fileExt, hasStego, stegoText, exifBytes, iccProfile, opts, alpha)
        del outPil
        psnr, shift = self._computeMetrics(origArr, outBytes)
        del origArr
        return outBytes, origW, origH, psnr, shift

    def _processImageViaSubprocess(
        self,
        rawBytes: bytes,
        fileExt: str,
        epsilon255: float,
        steps: int,
        stegoMode: str,
        stegoText: str,
        layers: Dict[str, bool],
        stepCb: Any,
        controlCb: Any,
        guidancePrompt: str,
        geoAnchorLow: float,
        geoAnchorHigh: float,
        temporalWeight: float,
        maskAugFactor: float,
        computeLevel: float,
        seed: int,
        opts: Dict[str, Any],
    ) -> Tuple[bytes, int, int, float, float]:
        """Runs PyTorch/CUDA optimization inside an isolated child process so unloadModel() frees 100% of CUDA/DLL RAM."""
        if not self.majorDepsReady:
            raise RuntimeError("Missing required dependencies. Open Configuration tab to install.")
        nowStamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        for plugin in self.algoMgr.selectRunnable(layers):
            CFG.algoLastUsed[plugin["id"]] = nowStamp

        RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
        ipcDir = RESULTS_ROOT
        if sys.platform != "win32":
            shmPath = Path("/dev/shm")
            try:
                if shmPath.is_dir() and os.access(shmPath, os.W_OK) and shutil.disk_usage(shmPath).free > 512 * (1024 ** 2):
                    ipcDir = shmPath
            except Exception:
                pass
        uid = uuid.uuid4().hex
        jobIn = ipcDir / f".lumiya_in_{uid}.tmp"
        jobOut = ipcDir / f".lumiya_out_{uid}.tmp"
        try:
            jobIn.write_bytes(rawBytes)
            if self.computeProc is None or self.computeProc.poll() is not None:
                startupInfo = None
                if sys.platform == "win32":
                    startupInfo = subprocess.STARTUPINFO()
                    startupInfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                workerErrPath = RESULTS_ROOT / ".worker.log"
                self.workerErrFile = open(workerErrPath, "w", encoding="utf-8", errors="replace")
                self.computeProc = subprocess.Popen(
                    [sys.executable, "-u", str(Path(__file__).resolve()), "--compute-worker"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=self.workerErrFile,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    cwd=str(ROOT_DIR),
                    startupinfo=startupInfo,
                )

            req = {
                "inPath": str(jobIn),
                "outPath": str(jobOut),
                "fileExt": fileExt,
                "epsilon255": epsilon255,
                "steps": steps,
                "stegoMode": stegoMode,
                "stegoText": stegoText,
                "layers": layers,
                "guidancePrompt": guidancePrompt,
                "geoAnchorLow": geoAnchorLow,
                "geoAnchorHigh": geoAnchorHigh,
                "temporalWeight": temporalWeight,
                "maskAugFactor": maskAugFactor,
                "computeLevel": computeLevel,
                "seed": seed,
                "stegoOpts": opts,
                "cfg": CFG.snapshotForStream(),
            }
            assert self.computeProc.stdin is not None and self.computeProc.stdout is not None
            self.computeProc.stdin.write(json.dumps(req) + "\n")
            self.computeProc.stdin.flush()

            while True:
                if controlCb() == "STOP":
                    self.unloadModel()
                    raise InterruptedError("Batch stopped by user.")
                line = self.computeProc.stdout.readline()
                if not line:
                    exitCode = self.computeProc.poll()
                    errLog = ""
                    try:
                        workerErrPath = RESULTS_ROOT / ".worker.log"
                        if workerErrPath.exists():
                            errLog = workerErrPath.read_text(encoding="utf-8", errors="replace").strip()
                    except Exception:
                        pass
                    self.unloadModel()
                    lastLine = errLog.splitlines()[-1] if errLog else ""
                    hint = f" [{lastLine}]" if lastLine else " (possible out-of-memory or killed by OS)"
                    raise RuntimeError(f"Compute worker process terminated unexpectedly (exit code {exitCode}){hint}.")
                line = line.rstrip("\r\n")
                if line.startswith("STEP\t"):
                    parts = line.split("\t")
                    if len(parts) >= 4:
                        s, tot, el = int(parts[1]), int(parts[2]), float(parts[3])
                        TermLog.progress(s, tot, el)
                        stepCb(s, tot, el)
                    if controlCb() == "STOP":
                        self.unloadModel()
                        raise InterruptedError("Batch stopped by user.")
                elif line.startswith("LOG\t"):
                    parts = line.split("\t", 3)
                    if len(parts) == 4:
                        TermLog.emit(parts[1], parts[2], parts[3])
                elif line.startswith("DONE\t"):
                    res = json.loads(line[5:])
                    outBytes = jobOut.read_bytes()
                    return outBytes, int(res["w"]), int(res["h"]), float(res["psnr"]), float(res["shift"])
                elif line.startswith("ERR\t"):
                    raise RuntimeError(line[4:])
        finally:
            for p in (jobIn, jobOut):
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass


def runServer(
    host: str = "127.0.0.1",
    port: int = 7860,
    debugMode: bool = False,
    noBrowser: bool = False,
    allowRemote: bool = False,
    authToken: str = "",
) -> None:
    if not os.environ.get("LUMIYA_BANNER_PRINTED"):
        print("  " + "=" * 100)
    TermLog.emit(
        f"{APP_NAME} {TermLog.CYAN}{APP_VERSION}{TermLog.RESET} // Python {sys.version.split()[0]}",
        "bootstrap.py",
        "INFO",
    )

    algoMgr = AlgoPluginManager(ALGOS_DIR, CFG, DEPS_STATUS, TermLog.emit)
    rebuilt = [k for k, item in algoMgr.plugins.items() if not item["notRebuilt"]]
    if not CFG.overrideHardware:
        CFG.favoriteAlgos = [k for k in CFG.favoriteAlgos if k in rebuilt] or rebuilt[:10]
    rt = RuntimeState(HISTORY_FILE, debugMode=debugMode, emulateExecution=debugMode)
    rt.loadHistory()
    app = ServerApp(
        cfg=CFG,
        configFile=CONFIG_FILE,
        deps=DEPS_STATUS,
        algoMgr=algoMgr,
        mon=TelemetryMonitor(DEPS_STATUS, CFG, psutil, NVIDIA_SMI_BIN),
        qMgr=QueueManager(RESULTS_ROOT, CFG),
        engine=ModularDefenseEngine(algoMgr),
        rt=rt,
        rootDir=ROOT_DIR,
        resultsRoot=RESULTS_ROOT,
        algosDir=ALGOS_DIR,
        identityDir=IDENTITY_DIR,
        themesDir=THEMES_DIR,
        uiFile=UI_FILE,
        manifestFile=MANIFEST_FILE,
        brandStatus=BRAND_STATUS,
        allowRemote=allowRemote,
        authToken=authToken,
        port=port,
    )
    app.executeBatch = lambda batchId: executeBatch(app, batchId)
    serve(app, host, port, noBrowser)


# One batch at a time: the GPU worker holds a single model and job.
_workerLock = threading.Lock()


def executeBatch(app: ServerApp, batchId: str) -> None:
    if not _workerLock.acquire(blocking=False):
        return
    try:
        batch = app.qMgr.batches.get(batchId)
        if not batch:
            return
        validFiles = [f for f in batch.files if f.valid and f.status in ("STAGED", "STOPPED", "FAILED")]
        if not validFiles:
            return

        # Snapshot batch parameters at launch so mid-run UI edits do not mutate an active batch
        snap = {
            "epsilon": float(batch.epsilon),
            "steps": int(batch.steps),
            "computeLevel": float(batch.computeLevel),
            "seed": int(batch.seed),
            "convertPng": bool(batch.convertPng),
            "stegoMode": str(batch.stegoMode),
            "stegoPayload": str(batch.stegoPayload),
            "stegoText": str(batch.stegoTextActive),
            "stegoMark": str(batch.stegoMarkActive),
            "stegoStrength": float(batch.stegoStrength),
            "stegoScale": float(batch.stegoScale),
            "stegoPlacement": str(batch.stegoPlacement),
            "layers": copy.deepcopy(batch.layers),
            "guidancePrompt": str(batch.guidancePrompt),
            "geoAnchorLow": float(batch.geoAnchorLow),
            "geoAnchorHigh": float(batch.geoAnchorHigh),
            "temporalWeight": float(batch.temporalWeight),
            "maskAugFactor": float(batch.maskAugFactor),
        }

        batch.state = "RUNNING"
        batch.exportDir.mkdir(parents=True, exist_ok=True)
        app.rt.busy = True
        app.rt.paused = False
        app.rt.stopRequested = False
        app.rt.activeBatch = batch.batchId
        app.rt.total = len(validFiles)
        app.qMgr.rev += 1
        doneCount = 0
        errCount = 0

        for idx, qfile in enumerate(validFiles, start=1):
            if app.rt.stopRequested:
                qfile.status = "STOPPED"
                app.qMgr.rev += 1
                continue

            qfile.status = "RUNNING"
            app.qMgr.rev += 1
            app.rt.idx = idx
            app.rt.currentFile = qfile.name
            app.rt.step = 0
            app.rt.steps = snap["steps"]

            def stepCb(s: int, tot: int, el: float) -> None:
                app.rt.step = s
                app.rt.steps = tot
                app.rt.stepRate = s / max(el, 1e-4)
                pct = s / max(tot, 1)
                app.rt.eta = (el / pct - el) if pct > 0 else 0.0

            def ctrlCb() -> str:
                if app.rt.stopRequested:
                    return "STOP"
                if batch.state != "RUNNING":
                    batch.state = "RUNNING"
                    app.qMgr.rev += 1
                return "RUN"

            try:
                tFile = time.time()
                outExt = ".png" if snap["convertPng"] else qfile.ext
                outBytes, w, h, psnr, shift = app.engine.processImage(
                    qfile.rawBytes,
                    fileExt=outExt,
                    epsilon255=snap["epsilon"],
                    steps=snap["steps"],
                    computeLevel=snap["computeLevel"],
                    seed=snap["seed"],
                    stegoOpts={
                        "payload": snap["stegoPayload"],
                        "mark": snap["stegoMark"],
                        "strength": snap["stegoStrength"],
                        "scale": snap["stegoScale"],
                        "placement": snap["stegoPlacement"],
                    },
                    stegoMode=snap["stegoMode"],
                    stegoText=snap["stegoText"],
                    layers=snap["layers"],
                    stepCb=stepCb,
                    controlCb=ctrlCb,
                    emulateDebug=app.rt.emulateExecution,
                    guidancePrompt=snap["guidancePrompt"],
                    geoAnchorLow=snap["geoAnchorLow"],
                    geoAnchorHigh=snap["geoAnchorHigh"],
                    temporalWeight=snap["temporalWeight"],
                    maskAugFactor=snap["maskAugFactor"],
                )
                # A redo gets a new file name, so earlier exports and their History rows stay intact.
                stem = Path(sanitizeFilename(qfile.name)).stem
                outPath = batch.exportDir / f"{stem}_lumiya{outExt}"
                counter = 1
                while outPath.exists():
                    outPath = batch.exportDir / f"{stem}_lumiya_{counter}{outExt}"
                    counter += 1
                outPath.write_bytes(outBytes)
                qfile.outPath = str(outPath)
                qfile.hasStego = snap["stegoMode"] in ("combined", "only") and bool(
                    snap["stegoText"].strip() or snap["stegoMark"]
                )
                qfile.psnr = psnr
                qfile.shift = shift
                qfile.exportRev += 1
                qfile.status = "DONE"
                doneCount += 1
                app.qMgr.rev += 1

                dtFile = time.time() - tFile
                TermLog.emit(
                    f"Exported {TermLog.GREEN}\"{outPath.name}\"{TermLog.RESET} ({w}x{h}, {psnr:.1f}dB) in {dtFile:.2f}s",
                    "ioHandler.py",
                    "OK",
                )

                app.rt.history.insert(
                    0,
                    {
                        "name": outPath.name,
                        "batch": batch.batchId,
                        "size": f"{w}x{h}",
                        "psnr": f"{psnr:.1f}",
                        "shift": f"{shift:.1f}",
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    },
                )
                app.rt.saveHistory()
            except InterruptedError:
                qfile.status = "STOPPED"
                batch.state = "STOPPED"
                app.qMgr.rev += 1
                break
            except Exception as exc:
                qfile.status = "FAILED"
                qfile.errorMsg = str(exc)
                errCount += 1
                app.qMgr.rev += 1
                TermLog.emit(f"Error processing {qfile.name}: {exc}", "worker.py", "ERROR")

        if app.rt.stopRequested or batch.state == "STOPPED":
            batch.state = "STOPPED"
        elif doneCount == 0 and errCount > 0:
            batch.state = "FAILED"
        else:
            batch.state = "COMPLETED"
        app.qMgr.rev += 1

        app.algoMgr.rev += 1
        CFG.save(CONFIG_FILE)
    finally:
        try:
            cleanMemoryAndStorage(ROOT_DIR, app.resultsRoot, app.qMgr.batches, app.engine, clearRawBytes=False)
        except Exception:
            pass
        app.rt.busy = False
        app.rt.paused = False
        app.rt.stopRequested = False
        app.rt.activeBatch = "-"
        app.rt.currentFile = "Idle"
        app.rt.step = 0
        app.rt.eta = 0.0
        app.rt.stepRate = 0.0
        _workerLock.release()


def runComputeWorker() -> None:
    """Dedicated child process for PyTorch/CUDA execution; exits on batch completion or cleaner run so OS reclaims 100% of RAM."""
    realIn = sys.stdin
    realOut = sys.stdout
    sys.stdout = sys.stderr

    def workerEmit(msg: str, module: str = "engine.py", level: str = "INFO") -> None:
        try:
            realOut.write(f"LOG\t{msg}\t{module}\t{level}\n")
            realOut.flush()
        except Exception:
            pass

    TermLog.emit = staticmethod(workerEmit)  # type: ignore[assignment]
    TermLog.progress = staticmethod(lambda *a, **kw: None)  # type: ignore[assignment]

    algoMgr = AlgoPluginManager(ALGOS_DIR, CFG, DEPS_STATUS, workerEmit)
    engine = ModularDefenseEngine(algoMgr, useSubprocess=False)

    for rawLine in realIn:
        line = rawLine.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            if isinstance(req.get("cfg"), dict):
                CFG.applyDict(req["cfg"])
            rawBytes = Path(req["inPath"]).read_bytes()

            def onStep(s: int, tot: int, el: float) -> None:
                realOut.write(f"STEP\t{s}\t{tot}\t{el:.4f}\n")
                realOut.flush()

            outBytes, w, h, psnr, shift = engine.processImage(
                rawBytes=rawBytes,
                fileExt=str(req["fileExt"]),
                epsilon255=float(req["epsilon255"]),
                steps=int(req["steps"]),
                stegoMode=str(req["stegoMode"]),
                stegoText=str(req["stegoText"]),
                layers=dict(req["layers"]),
                stepCb=onStep,
                controlCb=lambda: "RUN",
                emulateDebug=False,
                guidancePrompt=str(req.get("guidancePrompt", "")),
                geoAnchorLow=float(req.get("geoAnchorLow", 1.7)),
                geoAnchorHigh=float(req.get("geoAnchorHigh", 7.1)),
                temporalWeight=float(req.get("temporalWeight", 0.5)),
                maskAugFactor=float(req.get("maskAugFactor", 1.0)),
                computeLevel=float(req.get("computeLevel", 1.0)),
                seed=int(req.get("seed", 0)),
                stegoOpts=dict(req.get("stegoOpts") or {}),
            )
            Path(req["outPath"]).write_bytes(outBytes)
            realOut.write("DONE\t" + json.dumps({"w": w, "h": h, "psnr": psnr, "shift": shift}) + "\n")
            realOut.flush()
        except BaseException as exc:
            import traceback
            tbFull = traceback.format_exc().strip()
            TermLog.writeErrorLog("Compute Worker Exception", tbFull, module="computeWorker.py")
            tb = tbFull.splitlines()
            lastErr = tb[-1] if tb else str(exc)
            realOut.write(f"ERR\t{lastErr}\n")
            realOut.flush()


def runDoctor() -> None:
    """Prints a cross-distro diagnostic of Python, PyTorch, CUDA, NVML, vector fonts, temp storage, and algorithms."""
    import tempfile
    from stego.mark import _FONT_CANDIDATES

    algoMgr = AlgoPluginManager(ALGOS_DIR, CFG, DEPS_STATUS, lambda *a, **kw: None)
    runnable = sum(1 for p in algoMgr.plugins.values() if not p["notRebuilt"] and not algoMgr.blockReason(p))
    totalRebuilt = sum(1 for p in algoMgr.plugins.values() if not p["notRebuilt"])
    fontPath = next((c for c in _FONT_CANDIDATES if Path(c).exists()), "Fallback (fc-match / default)")
    tmpDir = Path(tempfile.gettempdir())
    try:
        tmpFreeGb = round(shutil.disk_usage(tmpDir).free / (1024 ** 3), 2)
    except Exception:
        tmpFreeGb = -1.0

    print("  " + "=" * 96)
    TermLog.emit(f"Python Runtime     : {sys.version.split()[0]} ({sys.executable})", "doctor.py", "OK")
    TermLog.emit(
        f"PyTorch / CUDA     : {DEPS_STATUS['versions']['torch']} / CUDA {DEPS_STATUS['versions']['cuda']} ({DEPS_STATUS['gpuName']}, {DEPS_STATUS['vramGb']} GB)",
        "doctor.py",
        "OK" if DEPS_STATUS["cuda"] else "WARNING",
    )
    TermLog.emit(f"Active Temp Dir    : {tmpDir} ({tmpFreeGb} GB free)", "doctor.py", "OK" if tmpFreeGb >= 4.0 else "WARNING")
    TermLog.emit(f"Results Directory  : {RESULTS_ROOT}", "doctor.py", "OK")
    TermLog.emit(f"Vector Font Source : {fontPath}", "doctor.py", "OK")
    TermLog.emit(f"Runnable Algos     : {runnable}/{totalRebuilt} ready on current hardware tier", "doctor.py", "OK")
    print("  " + "=" * 96)


def runHeadlessCli(args: argparse.Namespace) -> None:
    """Executes photo protection directly from the command line without launching the HTTP WebUI."""
    inTarget = Path(args.input).resolve() if args.input else None
    if not inTarget or not inTarget.exists():
        TermLog.emit("Headless mode requires a valid --input (-i) file or directory.", "cli.py", "ERROR")
        sys.exit(1)
    files = [inTarget] if inTarget.is_file() else sorted(p for p in inTarget.iterdir() if p.is_file() and p.suffix.lower() in VALID_EXTS)
    if not files:
        TermLog.emit(f"No supported image files found in {inTarget}", "cli.py", "ERROR")
        sys.exit(1)

    outDir = Path(args.output).resolve() if args.output else (RESULTS_ROOT / datetime.now().strftime("cli_%Y-%m-%d_%H-%M-%S"))
    outDir.mkdir(parents=True, exist_ok=True)
    algoMgr = AlgoPluginManager(ALGOS_DIR, CFG, DEPS_STATUS, TermLog.emit)
    engine = ModularDefenseEngine(algoMgr, useSubprocess=False)

    requestedAlgos = [a.strip().lower() for a in (args.algo or "photoguard").split(",") if a.strip()]
    layers = {k: (k.lower() in requestedAlgos) for k in algoMgr.plugins}
    if not any(layers.values()):
        TermLog.emit(f"Unknown --algo '{args.algo}'. Available: {', '.join(sorted(algoMgr.plugins))}", "cli.py", "ERROR")
        sys.exit(1)

    stegoText = (args.stego_text or "").strip()
    stegoMode = "combined" if stegoText else "off"
    budget = clampSetting("epsilon", args.budget, CFG.epsilon)
    steps = clampSetting("steps", args.steps, CFG.steps)

    for idx, fPath in enumerate(files, start=1):
        TermLog.emit(f"[{idx}/{len(files)}] Protecting {fPath.name} (budget={budget}/255, steps={steps})...", "cli.py", "INFO")
        outBytes, w, h, psnr, shift = engine.processImage(
            rawBytes=fPath.read_bytes(),
            fileExt=fPath.suffix.lower(),
            epsilon255=budget,
            steps=steps,
            stegoMode=stegoMode,
            stegoText=stegoText,
            layers=layers,
            stepCb=lambda s, tot, el: None,
            controlCb=lambda: "RUN",
            emulateDebug=args.debug,
        )
        dest = outDir / f"{fPath.stem}_lumiya{fPath.suffix.lower()}"
        dest.write_bytes(outBytes)
        TermLog.emit(f"Saved {dest} ({w}x{h}, {psnr:.1f}dB, maxShift={shift:.1f})", "cli.py", "OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=f"{APP_NAME} {APP_VERSION} - Evaluative Suite")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="WebUI HTTP listening interface (default: 127.0.0.1)")
    parser.add_argument("--listen", action="store_true", help="Bind to 0.0.0.0 to allow access from local network or remote machines")
    parser.add_argument("-p", "--port", type=int, default=7860, help="WebUI HTTP listening port (default: 7860)")
    parser.add_argument("--auth-token", type=str, default="", help="Require access token for WebUI API requests")
    parser.add_argument("--debug", action="store_true", help="Launch in interactive debug / emulation mode")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically launch system browser on startup")
    parser.add_argument("--cluster", action="store_true", help="Shared cluster/HPC preset (--no-browser, smart TMPDIR, /dev/shm IPC)")
    parser.add_argument("--tmp-dir", type=str, default="", help="Override temporary directory (TMPDIR)")
    parser.add_argument("--cache-dir", type=str, default="", help="Override PyTorch/HuggingFace/pip cache directory")
    parser.add_argument("--results-dir", type=str, default="", help="Override exported results directory")
    parser.add_argument("--device", type=str, choices=("auto", "cuda", "cpu"), default="", help="Force compute target (auto, cuda, cpu)")
    parser.add_argument("--gpu", type=str, default="", help="Select GPU index (sets CUDA_VISIBLE_DEVICES)")
    parser.add_argument("--tile-size", type=int, default=0, help="Override spatial PGD tile size (256-1024)")
    parser.add_argument("--low-vram", action="store_true", help="Enable low-VRAM optimizations (512px tiles, fp16, RAM spillover)")
    parser.add_argument("--doctor", action="store_true", help="Run cross-distro hardware, CUDA, font, and storage diagnostics")
    parser.add_argument("--update", action="store_true", help="Run protected GitHub self-pull and dependency update")
    parser.add_argument("--integrity", action="store_true", help="Verify SHA-256 and MD5 checksums against core/integrity.lmy")
    parser.add_argument("--clean", action="store_true", help="Purge temporary files, __pycache__, and IPC staging")
    parser.add_argument("--headless", action="store_true", help="Run batch protection directly in CLI without starting WebUI")
    parser.add_argument("-i", "--input", type=str, default="", help="Input image file or directory for --headless mode")
    parser.add_argument("-o", "--output", type=str, default="", help="Output directory for --headless mode")
    parser.add_argument("--algo", type=str, default="photoguard", help="Comma-separated algorithm IDs for --headless mode")
    parser.add_argument("--budget", type=float, default=CFG.epsilon, help="Perturbation budget (1-32) for --headless mode")
    parser.add_argument("--steps", type=int, default=CFG.steps, help="Optimization steps for --headless mode")
    parser.add_argument("--stego-text", type=str, default="", help="Optional watermark text for --headless mode")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--compute-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--uninstall", action="store_true", help="Remove this program footprint dependencies (default: manifest cleanup)")
    parser.add_argument("--purge", action="store_true", help="Thoroughly purge runtime pillars")
    args = parser.parse_args()

    if args.results_dir:
        RESULTS_ROOT = Path(args.results_dir).resolve()
        RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    if args.device:
        CFG.computeBackend = args.device
    if args.tile_size:
        CFG.workingDim = safeInt(args.tile_size, CFG.workingDim, 256, 1024)
    if args.low_vram:
        CFG.workingDim = min(CFG.workingDim, 512)
        CFG.precision = "fp16"
        CFG.allowRamSpillover = True
    if args.cluster:
        args.no_browser = True

    if args.uninstall or args.purge:
        flag = "--purge" if args.purge else "--manifest"
        if sys.platform == "win32":
            subprocess.run([str(ROOT_DIR / "uninstall.bat"), flag, "-y"], cwd=str(ROOT_DIR))
        else:
            subprocess.run(["bash", str(ROOT_DIR / "run.sh"), "uninstall", flag, "-y"], cwd=str(ROOT_DIR))
        sys.exit(0)
    if args.update:
        res = runProtectedUpdate(ROOT_DIR, sys.executable, APP_VERSION)
        lvl = "OK" if res.get("ok") else "ERROR"
        TermLog.emit(str(res.get("message") or res.get("error") or "Update finished."), "updater.py", lvl)
        sys.exit(0 if res.get("ok") else 1)
    if args.integrity:
        rep = computeProgramIntegrity(ROOT_DIR, APP_VERSION)
        for k in ("master", "core", "scripts"):
            g = rep["lumpSums"][k]
            TermLog.emit(
                f"{g['key']:<16} ({g['count']} files)  SHA-256: {g['sha256'][:16]}...  MD5: {g['md5']}",
                "updater.py",
                "OK" if g["status"] == "VERIFIED" else "ERROR",
            )
        if rep.get("ok"):
            TermLog.emit("✔ You're good! All tracked files match core/integrity.lmy.", "updater.py", "OK")
            sys.exit(0)
        TermLog.emit(f"Integrity mismatch in: {', '.join(rep.get('mismatches', []))}", "updater.py", "ERROR")
        sys.exit(1)
    if args.clean:
        rep = cleanMemoryAndStorage(ROOT_DIR, RESULTS_ROOT, {}, None, clearRawBytes=True)
        TermLog.emit(f"Cleaned workspace ({rep.get('removedFiles', 0)} temp files removed).", "cleaner.py", "OK")
        sys.exit(0)
    if args.doctor:
        runDoctor()
        sys.exit(0)
    if args.headless:
        runHeadlessCli(args)
        sys.exit(0)

    bindHost = "0.0.0.0" if args.listen else args.host
    allowRemote = bool(args.listen or bindHost in ("0.0.0.0", "::"))
    authToken = args.auth_token or os.environ.get("LUMIYA_AUTH_TOKEN", "")
    if allowRemote and not authToken and not args.compute_worker:
        # Without a token, any machine on the network could drive the app; the launcher passes this one to the worker.
        authToken = secrets.token_urlsafe(24)
    if args.compute_worker:
        runComputeWorker()
    elif args.worker:
        runServer(
            host=bindHost,
            port=args.port,
            debugMode=args.debug,
            noBrowser=args.no_browser,
            allowRemote=allowRemote,
            authToken=authToken,
        )
    else:
        targetPort = findAvailablePort(args.port, host=bindHost)
        firstLaunch = not args.no_browser
        while True:
            cmd = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker",
                "--host",
                bindHost,
                "--port",
                str(targetPort),
            ]
            if args.listen:
                cmd.append("--listen")
            if authToken:
                cmd.extend(["--auth-token", authToken])
            if args.debug:
                cmd.append("--debug")
            if args.cluster:
                cmd.append("--cluster")
            if args.low_vram:
                cmd.append("--low-vram")
            if args.device:
                cmd.extend(["--device", args.device])
            if args.tile_size:
                cmd.extend(["--tile-size", str(args.tile_size)])
            if args.results_dir:
                cmd.extend(["--results-dir", str(RESULTS_ROOT)])
            if not firstLaunch:
                cmd.append("--no-browser")
            childProc = subprocess.Popen(cmd, cwd=str(ROOT_DIR))
            try:
                rc = childProc.wait()
            except KeyboardInterrupt:
                childProc.kill()
                print("\n  [SHUTDOWN] Exiting Lumiya launcher (Ctrl+C)...", flush=True)
                break
            firstLaunch = False
            if rc != 42:
                break
            time.sleep(0.25)
