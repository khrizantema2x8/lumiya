from __future__ import annotations

import argparse
import base64
import copy
import ctypes
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.cleaner import cleanMemoryAndStorage
from core.init import (
    DEFAULT_ALGO_IDS,
    MAX_STEPS,
    VALID_EXTS,
    AlgoPluginManager,
    SuiteConfig,
    TelemetryMonitor,
    atomicWrite,
    isTrustedRequest,
    openPathForeground,
    parseJsonBody,
    safeFloat,
    safeInt,
    sanitizeFilename,
    verifyBrandAssets,
)
from stego.mark import PLACEMENTS, MarkError, embedMark, inspectStego, prepareMark

# The progress bar uses block characters a legacy console codepage cannot encode.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

APP_NAME = "PORTtralica Lumiya"
APP_VERSION = "v0.6.021.4330 (Pilot)"

if sys.platform == "win32":
    kernel32 = ctypes.windll.kernel32
    stdOutHandle = kernel32.GetStdHandle(-11)
    consoleMode = ctypes.c_ulong()
    if kernel32.GetConsoleMode(stdOutHandle, ctypes.byref(consoleMode)):
        kernel32.SetConsoleMode(stdOutHandle, consoleMode.value | 0x0004)


class TermLog:
    RESET = "\x1b[0m"
    DIM = "\x1b[90m"
    CYAN = "\x1b[96m"
    GREEN = "\x1b[92m"
    YELLOW = "\x1b[93m"
    RED = "\x1b[91m"
    MAGENTA = "\x1b[95m"
    WHITE = "\x1b[97m"
    WIDTH = 96

    @classmethod
    def emit(cls, msg: str, module: str = "lumiyaCore.py", level: str = "INFO") -> None:
        lvlColor = {
            "INFO": cls.CYAN,
            "WARNING": cls.YELLOW,
            "ERROR": cls.RED,
            "OK": cls.GREEN,
        }.get(level, cls.CYAN)

        cleanText = msg
        for code in (cls.RESET, cls.DIM, cls.CYAN, cls.GREEN, cls.YELLOW, cls.RED, cls.MAGENTA, cls.WHITE):
            cleanText = cleanText.replace(code, "")

        rightTag = f"{cls.DIM}{module} :: {lvlColor}{level}{cls.RESET}"
        rightLen = len(f"{module} :: {level}")
        padCount = max(2, cls.WIDTH - len(cleanText) - rightLen)
        sys.stdout.write(f"\r\x1b[2K{msg}{' ' * padCount}{rightTag}\n")
        sys.stdout.flush()

    @classmethod
    def progress(cls, step: int, total: int, elapsed: float) -> None:
        pct = int(round((step / max(total, 1)) * 100))
        barWidth = 42
        filled = int(round(barWidth * (step / max(total, 1))))
        barStr = "\u2588" * filled + " " * (barWidth - filled)
        rate = step / max(elapsed, 1e-4)
        rem = (total - step) / max(rate, 1e-4)
        minEl, secEl = divmod(int(elapsed), 60)
        minRem, secRem = divmod(int(rem), 60)
        rateStr = f"{rate:5.2f}it/s" if rate >= 1.0 else f"{1.0 / max(rate, 1e-4):5.2f}s/it"
        line = (
            f"{pct:3d}%|{cls.WHITE}{barStr}{cls.RESET}| "
            f"{step}/{total} [{minEl:02d}:{secEl:02d}<{minRem:02d}:{secRem:02d}, {rateStr}]"
        )
        sys.stdout.write(f"\r\x1b[2K{line}")
        if step >= total:
            sys.stdout.write("\n")
        sys.stdout.flush()


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
    "recommended": {
        "python": "3.12.x - 3.13.x",
        "torch": "2.6.0+ (build matched to driver)",
        "cuda": "Matched to driver (12.4+)",
        "diffusers": "0.32.2+",
        "transformers": "4.48.0+",
        "pil": ">= 10.4.0",
        "psutil": ">= 6.0.0",
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
        except Exception:
            pass
    elif DEPS_STATUS["torch"]:
        gpuDetected = False
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
            gpuName, memMb = [x.strip() for x in firstLine.split(",", 1)]
            tVer = str(DEPS_STATUS["versions"]["torch"])
            hasCuBuild = ("+cpu" not in tVer.lower())
            if gpuName and hasCuBuild:
                gpuDetected = True
                DEPS_STATUS["cuda"] = True
                DEPS_STATUS["versions"]["cuda"] = f'{tVer.split("+cu")[-1][:-1]}.{tVer[-1]}' if "+cu" in tVer else "Unknown"
                DEPS_STATUS["gpuName"] = gpuName
                try:
                    DEPS_STATUS["vramGb"] = round(float(memMb.split()[0]) / 1024.0, 2)
                except Exception:
                    DEPS_STATUS["vramGb"] = 8.0
        except Exception:
            pass

        if not gpuDetected:
            try:
                startupInfo = None
                if sys.platform == "win32":
                    startupInfo = subprocess.STARTUPINFO()
                    startupInfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                probeJson = subprocess.check_output(
                    [
                        sys.executable,
                        "-c",
                        (
                            "import json, torch; "
                            "ok = bool(torch.cuda.is_available()); "
                            "print(json.dumps({"
                            "'cuda': ok, "
                            "'ver': str(torch.version.cuda or 'Unknown'), "
                            "'name': torch.cuda.get_device_name(0) if ok else 'CPU', "
                            "'vram': round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 2) if ok else 0.0"
                            "}))"
                        ),
                    ],
                    startupinfo=startupInfo,
                    stderr=subprocess.DEVNULL,
                    timeout=15.0,
                ).decode("utf-8", errors="replace").strip()
                info = json.loads(probeJson.splitlines()[-1])
                if info.get("cuda"):
                    gpuDetected = True
                    DEPS_STATUS["cuda"] = True
                    DEPS_STATUS["versions"]["cuda"] = info.get("ver", "Unknown")
                    DEPS_STATUS["gpuName"] = info.get("name", "NVIDIA GPU")
                    DEPS_STATUS["vramGb"] = float(info.get("vram", 0.0))
            except Exception:
                pass

        if gpuDetected:
            if DEPS_STATUS["vramGb"] < 2.0:
                DEPS_STATUS["hardwareAdvisory"] = True
                DEPS_STATUS["advisoryReason"] = f"Detected GPU ({DEPS_STATUS['gpuName']}) has under 2.0 GB VRAM."
        else:
            DEPS_STATUS["hardwareAdvisory"] = True
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
USER_DIR = ROOT_DIR / "user"
UI_FILE = ROOT_DIR / "ui.html"
CONFIG_FILE = USER_DIR / "config.json"
HISTORY_FILE = USER_DIR / "history.json"
MANIFEST_FILE = USER_DIR / "install_manifest.log"

BRAND_STATUS = verifyBrandAssets(ROOT_DIR)
CFG = SuiteConfig.load(CONFIG_FILE)


def workingSizes(width: int, height: int, vramGb: float, allowRamSpillover: bool = True) -> List[Tuple[int, int]]:
    """Editor input sizes: geometric grid up to native/VRAM-supported resolution."""
    topMp = min(4.2, 2.1 if (allowRamSpillover or vramGb >= 8.0) else 0.8)
    pixels = max(64, width * height)
    sizes = []
    mp = min(topMp, 0.5)
    while True:
        scale = min(1.0, math.sqrt(mp * 1e6 / pixels))
        size = (max(8, round(height * scale / 8) * 8), max(8, round(width * scale / 8) * 8))
        if size not in sizes:
            sizes.append(size)
        if mp >= topMp:
            return sizes
        mp = min(topMp, mp * 1.96)


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


@dataclass
class QueuedFile:
    fileId: str
    name: str
    ext: str
    sha256: str
    sizeBytes: int
    width: int = 0
    height: int = 0
    valid: bool = True
    errorMsg: str = ""
    status: str = "STAGED"
    rawBytes: bytes = b""
    thumbB64: str = ""
    outPath: str = ""
    hasStego: bool = False
    psnr: float = 0.0
    shift: float = 0.0
    exportRev: int = 0


@dataclass
class BatchQueue:
    batchId: str
    createdAt: str
    state: str = "STAGED"
    epsilon: float = field(default_factory=lambda: CFG.epsilon)
    computeLevel: float = field(default_factory=lambda: CFG.computeLevel)
    seed: int = field(default_factory=lambda: CFG.seed)
    steps: int = field(default_factory=lambda: CFG.steps)
    guidancePrompt: str = field(default_factory=lambda: CFG.guidancePrompt)
    geoAnchorLow: float = field(default_factory=lambda: CFG.geoAnchorLow)
    geoAnchorHigh: float = field(default_factory=lambda: CFG.geoAnchorHigh)
    temporalWeight: float = field(default_factory=lambda: CFG.temporalWeight)
    maskAugFactor: float = field(default_factory=lambda: CFG.maskAugFactor)
    convertPng: bool = field(default_factory=lambda: CFG.convertPng)
    stegoMode: str = field(default_factory=lambda: CFG.stegoMode)
    stegoText: str = field(default_factory=lambda: CFG.stegoText)
    stegoStrength: float = field(default_factory=lambda: CFG.stegoStrength)
    stegoScale: float = field(default_factory=lambda: CFG.stegoScale)
    stegoPlacement: str = field(default_factory=lambda: CFG.stegoPlacement)
    stegoPayload: str = field(default_factory=lambda: CFG.stegoPayload)
    stegoMark: str = field(default_factory=lambda: CFG.stegoMark)
    layers: Dict[str, bool] = field(default_factory=lambda: dict(CFG.layers))
    files: List[QueuedFile] = field(default_factory=list)

    @property
    def stegoTextActive(self) -> str:
        return self.stegoText if self.stegoPayload in ("text", "binary") else ""

    @property
    def stegoMarkActive(self) -> str:
        return self.stegoMark if self.stegoPayload == "image" else ""

    @property
    def exportDir(self) -> Path:
        return RESULTS_ROOT / self.batchId

    @property
    def hasExported(self) -> bool:
        return any(bool(f.outPath) for f in self.files)


def validateBatchConfig(batch: BatchQueue, algoMgr: Optional[AlgoPluginManager] = None, requireFiles: bool = False) -> Tuple[bool, str]:
    """Ensures batch parameters, hardware constraints, and algorithm selections are valid before execution or save."""
    if requireFiles:
        validFiles = [f for f in batch.files if f.valid]
        if not validFiles:
            return False, "This batch contains no valid readable images to process."
    if not (1.0 <= float(batch.epsilon) <= 32.0):
        return False, "Budget must be between 1 and 32."
    if not (0.0 <= float(batch.temporalWeight) <= 1.0):
        return False, "Temporal weight must be between 0.0 and 1.0."
    if not (0.2 <= float(batch.maskAugFactor) <= 2.0):
        return False, "Mask augmentation factor must be between 0.2 and 2.0."
    if batch.stegoMode not in ("off", "combined", "only"):
        return False, f"Invalid defense mode '{batch.stegoMode}'."
    if batch.stegoMode != "only":
        enabledIds = [k for k, v in (batch.layers or {}).items() if bool(v)]
        if not enabledIds:
            return False, "At least one AI-Defense Layers algorithm must be enabled when AI-blocking is active."
        if algoMgr is not None:
            runnableCount = 0
            lastBlockReason = ""
            for aid in enabledIds:
                p = algoMgr.plugins.get(aid)
                if not p:
                    continue
                bReason = algoMgr.blockReason(p)
                if bReason:
                    lastBlockReason = f"{p.get('name', aid)}: {bReason}"
                else:
                    runnableCount += 1
            if runnableCount == 0 and lastBlockReason:
                return False, lastBlockReason
    if batch.stegoMode in ("combined", "only"):
        if batch.stegoPayload in ("text", "binary") and not str(batch.stegoTextActive or "").strip():
            return False, "Enter a watermark text payload when text steganography is enabled."
        if batch.stegoPayload == "image" and not batch.stegoMarkActive:
            return False, "Import a transparent PNG mark when Visible Image Mark steganography is enabled."
    return True, ""


class QueueManager:
    def __init__(self) -> None:
        RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.batches: Dict[str, BatchQueue] = {}
        self.batchOrder: List[str] = []
        self.rev: int = 1

    def createNewBatch(self) -> BatchQueue:
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        bid = stamp
        idx = 1
        while bid in self.batches or (RESULTS_ROOT / bid).exists():
            bid = f"{stamp}_{idx}"
            idx += 1
        batch = BatchQueue(batchId=bid, createdAt=datetime.now().strftime("%H:%M:%S"))
        self.batches[bid] = batch
        self.batchOrder.append(bid)
        self.rev += 1
        TermLog.emit(f"Created staging batch {TermLog.CYAN}{bid}{TermLog.RESET}", "queueManager.py", "INFO")
        return batch

    def createOrGetStagingBatch(self) -> BatchQueue:
        with self.lock:
            for bid in reversed(self.batchOrder):
                b = self.batches[bid]
                if b.state == "STAGED":
                    return b
            return self.createNewBatch()

    def addFile(self, batchId: str, filename: str, data: bytes) -> Dict[str, Any]:
        safeName = sanitizeFilename(filename)
        ext = Path(safeName).suffix.lower()

        if ext not in VALID_EXTS:
            return {
                "accepted": False,
                "duplicate": False,
                "reason": f"Illegal format '{ext}' for '{safeName}'. Allowed: {', '.join(VALID_EXTS)}",
            }

        fileHash = hashlib.sha256(data).hexdigest()

        with self.lock:
            batch = self.batches.get(batchId)
            if batch is None or batch.state not in ("STAGED", "PAUSED", "STOPPED"):
                batch = self.createOrGetStagingBatch()

            for existing in batch.files:
                if existing.sha256 == fileHash:
                    return {
                        "accepted": False,
                        "duplicate": True,
                        "reason": f"Duplicate skipped: '{safeName}' is already in batch {batch.batchId}.",
                    }

        validContent = True
        errMsg = ""
        width, height = 0, 0
        thumbStr = ""
        if DEPS_STATUS["pil"]:
            try:
                with Image.open(io.BytesIO(data)) as verifyIm:
                    verifyIm.verify()
                with Image.open(io.BytesIO(data)) as im:
                    im = ImageOps.exif_transpose(im)
                    width, height = im.size
                    if width < 16 or height < 16:
                        raise ValueError(f"Dimensions too small ({width}x{height})")
                    thumb = im.convert("RGB")
                    thumb.thumbnail((220, 220))
                    buf = io.BytesIO()
                    thumb.save(buf, format="JPEG", quality=82)
                    thumbStr = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
            except Exception as exc:
                validContent = False
                errMsg = f"Corrupted image content: {exc}"
        else:
            width, height = 512, 512

        qfile = QueuedFile(
            fileId=uuid.uuid4().hex[:10],
            name=safeName,
            ext=ext,
            sha256=fileHash,
            sizeBytes=len(data),
            width=width,
            height=height,
            valid=validContent,
            errorMsg=errMsg,
            status="STAGED" if validContent else "CORRUPT",
            rawBytes=data if validContent else b"",
            thumbB64=thumbStr,
        )

        with self.lock:
            batch.files.append(qfile)
            self.rev += 1

        return {"accepted": True, "duplicate": False, "valid": validContent, "name": safeName, "batchId": batch.batchId}

    def reorderOrSplitFile(self, srcBatchId: str, fileId: str, targetBatchId: str, targetIndex: int) -> Dict[str, Any]:
        with self.lock:
            srcBatch = self.batches.get(srcBatchId)
            if not srcBatch:
                return {"ok": False}
            movedFile = None
            for idx, f in enumerate(srcBatch.files):
                if f.fileId == fileId:
                    movedFile = srcBatch.files.pop(idx)
                    break
            if not movedFile:
                return {"ok": False}

            if targetBatchId == "NEW_BATCH":
                destBatch = self.createNewBatch()
                destBatch.files.append(movedFile)
            else:
                destBatch = self.batches.get(targetBatchId, srcBatch)
                clampedIdx = max(0, min(targetIndex, len(destBatch.files)))
                destBatch.files.insert(clampedIdx, movedFile)

            if len(srcBatch.files) == 0:
                self.deleteBatchUnlocked(srcBatchId)

            self.rev += 1
            return {"ok": True}

    def getFileBytes(self, batchId: str, fileId: str, preferExport: bool = False) -> Optional[Tuple[bytes, str]]:
        with self.lock:
            b = self.batches.get(batchId)
            if not b:
                return None
            for f in b.files:
                if f.fileId == fileId:
                    if preferExport and f.outPath and Path(f.outPath).exists():
                        outExt = Path(f.outPath).suffix.lower()
                        outMime = "image/png" if outExt == ".png" else ("image/webp" if outExt == ".webp" else "image/jpeg")
                        return Path(f.outPath).read_bytes(), outMime
                    mime = "image/png" if f.ext == ".png" else ("image/webp" if f.ext == ".webp" else "image/jpeg")
                    if f.rawBytes:
                        return f.rawBytes, mime
                    if f.outPath and Path(f.outPath).exists():
                        outExt = Path(f.outPath).suffix.lower()
                        outMime = "image/png" if outExt == ".png" else ("image/webp" if outExt == ".webp" else "image/jpeg")
                        return Path(f.outPath).read_bytes(), outMime
            return None

    def removeFile(self, batchId: str, fileId: str) -> Dict[str, Any]:
        with self.lock:
            batch = self.batches.get(batchId)
            if not batch:
                return {"ok": False}
            batch.files = [f for f in batch.files if f.fileId != fileId]
            emptyNow = len(batch.files) == 0
            if emptyNow:
                self.deleteBatchUnlocked(batchId)
            self.rev += 1
            return {"ok": True, "batchDeleted": emptyNow}

    def deleteBatchUnlocked(self, batchId: str, deleteExports: bool = False) -> None:
        batch = self.batches.pop(batchId, None)
        if batchId in self.batchOrder:
            self.batchOrder.remove(batchId)
        if deleteExports and batch and batch.exportDir.exists():
            shutil.rmtree(batch.exportDir, ignore_errors=True)
        self.rev += 1

    def deleteBatch(self, batchId: str, keepExports: bool = False) -> bool:
        with self.lock:
            if batchId not in self.batches:
                return False
            self.deleteBatchUnlocked(batchId, deleteExports=not keepExports)
            return True

    def serializeTree(self) -> List[Dict[str, Any]]:
        with self.lock:
            out = []
            for bid in reversed(self.batchOrder):
                b = self.batches[bid]
                allPng = len(b.files) > 0 and all(f.ext.lower() == ".png" for f in b.files)
                out.append(
                    {
                        "batchId": b.batchId,
                        "createdAt": b.createdAt,
                        "state": b.state,
                        "hasExported": b.hasExported,
                        "allPng": allPng,
                        "convertPng": b.convertPng,
                        "epsilon": b.epsilon,
                        "computeLevel": b.computeLevel,
                        "seed": b.seed,
                        "stegoStrength": b.stegoStrength,
                        "stegoScale": b.stegoScale,
                        "stegoPlacement": b.stegoPlacement,
                        "stegoPayload": b.stegoPayload,
                        "stegoMark": b.stegoMark,
                        "steps": b.steps,
                        "guidancePrompt": b.guidancePrompt,
                        "geoAnchorLow": b.geoAnchorLow,
                        "geoAnchorHigh": b.geoAnchorHigh,
                        "temporalWeight": b.temporalWeight,
                        "maskAugFactor": b.maskAugFactor,
                        "stegoMode": b.stegoMode,
                        "stegoText": b.stegoText,
                        "layers": dict(b.layers),
                        "files": [
                            {
                                "fileId": f.fileId,
                                "name": f.name,
                                "ext": f.ext,
                                "dims": f"{f.width}x{f.height}" if f.width else "Invalid",
                                "sizeKb": round(f.sizeBytes / 1024.0, 1),
                                "valid": f.valid,
                                "errorMsg": f.errorMsg,
                                "status": f.status,
                                "hasStego": f.hasStego,
                                "hasExport": bool(f.outPath and Path(f.outPath).exists()),
                                "exportRev": f.exportRev,
                                "psnr": round(f.psnr, 1),
                                "shift": round(f.shift, 1),
                                "thumb": f.thumbB64,
                            }
                            for f in b.files
                        ],
                    }
                )
            return out


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
            totalSteps = 5 if stegoMode == "only" else steps
            for step in range(1, totalSteps + 1):
                if controlCb() == "STOP":
                    raise InterruptedError("Stopped")
                time.sleep(0.05)
                el = max(time.time() - tStart, 1e-4)
                TermLog.progress(step, totalSteps, el)
                stepCb(step, totalSteps, el)

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
                import numpy as np
                before = np.asarray(im, dtype=np.float64)
                after = np.asarray(Image.open(io.BytesIO(outBytes)).convert("RGB"), dtype=np.float64)
                mse = float(np.mean((after - before) ** 2))
                psnr = 10.0 * math.log10((255.0 ** 2) / max(mse, 1e-10))
                return outBytes, width, height, psnr, float(np.abs(after - before).max())
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
        for k, enabled in layers.items():
            plugin = self.algoMgr.plugins.get(k)
            if enabled and plugin and plugin["notRebuilt"]:
                reason = plugin.get("blockerReason") or f"{plugin['name']} is not rebuilt yet, so it cannot run."
                raise RuntimeError(reason)
            if enabled and plugin and not self.algoMgr.blockReason(plugin):
                CFG.algoLastUsed[k] = nowStamp
                mod = self.algoMgr.getPluginModule(k)
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
            deltaInt = torch.round(scaled).clamp(-limit, limit).permute(1, 2, 0).numpy()
        finally:
            ctx.clear()
            for k in [ck for ck in list(self.cache.keys()) if isinstance(ck[0], int) and ck[0] < 0]:
                self.cache.pop(k, None)
            del xOrig, limitMap, delta
            if device == "cuda" and torch is not None and torch.cuda.is_available():
                torch.cuda.empty_cache()
        origArr = np.asarray(origRgb, dtype=np.float64)
        outArr = np.clip(origArr + deltaInt, 0, 255).astype(np.uint8)
        outPil = Image.fromarray(outArr)
        hasStego = stegoMode == "combined" and hasStegoPayload
        outBytes = self.encodeOutputImage(outPil, fileExt, hasStego, stegoText, exifBytes, iccProfile, opts, alpha)
        finalArr = np.asarray(Image.open(io.BytesIO(outBytes)).convert("RGB"), dtype=np.float64)
        mse = float(np.mean((finalArr - origArr) ** 2))
        psnr = 10.0 * math.log10((255.0 ** 2) / max(mse, 1e-10))
        return outBytes, origW, origH, psnr, float(np.abs(finalArr - origArr).max())

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
        hasRunnable = False
        for k, enabled in layers.items():
            plugin = self.algoMgr.plugins.get(k)
            if enabled and plugin and plugin["notRebuilt"]:
                reason = plugin.get("blockerReason") or f"{plugin['name']} is not rebuilt yet, so it cannot run."
                raise RuntimeError(reason)
            if enabled and plugin and not self.algoMgr.blockReason(plugin):
                CFG.algoLastUsed[k] = nowStamp
                hasRunnable = True
        if not hasRunnable:
            raise RuntimeError("None of the selected algorithms can run on this system.")

        RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
        uid = uuid.uuid4().hex
        jobIn = RESULTS_ROOT / f".job_in_{uid}.tmp"
        jobOut = RESULTS_ROOT / f".job_out_{uid}.tmp"
        try:
            jobIn.write_bytes(rawBytes)
            if self.computeProc is None or self.computeProc.poll() is not None:
                startupInfo = None
                if sys.platform == "win32":
                    startupInfo = subprocess.STARTUPINFO()
                    startupInfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                self.computeProc = subprocess.Popen(
                    [sys.executable, "-u", str(Path(__file__).resolve()), "--compute-worker"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
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
                    self.unloadModel()
                    raise RuntimeError("Compute worker process terminated unexpectedly (possible out-of-memory).")
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


@dataclass
class RuntimeState:
    busy: bool = False
    paused: bool = False
    stopRequested: bool = False
    debugMode: bool = False
    emulateExecution: bool = False
    activeBatch: str = "-"
    currentFile: str = "Idle"
    idx: int = 0
    total: int = 0
    step: int = 0
    steps: int = CFG.steps
    eta: float = 0.0
    stepRate: float = 0.0
    history: List[Dict[str, Any]] = field(default_factory=list)

    def loadHistory(self) -> None:
        target = HISTORY_FILE if HISTORY_FILE.exists() else (ROOT_DIR / "history.json")
        if target.exists():
            try:
                self.history = json.loads(target.read_text(encoding="utf-8"))
            except Exception:
                self.history = []

    def saveHistory(self) -> None:
        try:
            atomicWrite(HISTORY_FILE, json.dumps(self.history[:100], indent=2))
        except Exception:
            pass

    def removeBatchHistory(self, batchId: str) -> None:
        beforeLen = len(self.history)
        self.history = [h for h in self.history if h.get("batch") != batchId]
        if len(self.history) != beforeLen:
            self.saveHistory()


def findAvailablePort(startPort: int = 7860, maxAttempts: int = 50) -> int:
    """Automatic Port Selection (APS): probes local sockets to find an available port."""
    for candidate in range(startPort, startPort + maxAttempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", candidate))
                return candidate
            except OSError:
                continue
    return startPort


def runServer(port: int = 7860, debugMode: bool = False, noBrowser: bool = False) -> None:
    actualPort = port
    print("=" * 96)
    TermLog.emit(
        f"{APP_NAME} {TermLog.CYAN}{APP_VERSION}{TermLog.RESET} // Python {sys.version.split()[0]}",
        "bootstrap.py",
        "INFO",
    )

    algoMgr = AlgoPluginManager(ALGOS_DIR, CFG, DEPS_STATUS, TermLog.emit)
    rebuilt = [k for k, item in algoMgr.plugins.items() if not item["notRebuilt"]]
    if not CFG.overrideHardware:
        CFG.favoriteAlgos = [k for k in CFG.favoriteAlgos if k in rebuilt] or rebuilt[:10]
    mon = TelemetryMonitor(DEPS_STATUS, CFG, psutil, NVIDIA_SMI_BIN)
    qMgr = QueueManager()
    engine = ModularDefenseEngine(algoMgr)
    rt = RuntimeState(debugMode=debugMode, emulateExecution=debugMode)
    rt.loadHistory()
    workerLock = threading.Lock()
    sseLock = threading.Lock()
    activeSseCount = 0

    def triggerLastTabPurge() -> None:
        time.sleep(1.5)
        with sseLock:
            stillZero = activeSseCount == 0
        if stillZero and not rt.busy:
            rep = cleanMemoryAndStorage(ROOT_DIR, RESULTS_ROOT, qMgr.batches, engine, clearRawBytes=True)
            TermLog.emit(
                f"No active browser tabs — purged caches (VRAM freed: {rep['vramFreedMb']} MB, buffers: {rep['ramBuffersCleared']})",
                "core/cleaner.py",
                "INFO",
            )

    def executeBatch(batchId: str) -> None:
        if not workerLock.acquire(blocking=False):
            return
        try:
            batch = qMgr.batches.get(batchId)
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
            rt.busy = True
            rt.paused = False
            rt.stopRequested = False
            rt.activeBatch = batch.batchId
            rt.total = len(validFiles)
            qMgr.rev += 1
            doneCount = 0
            errCount = 0

            for idx, qfile in enumerate(validFiles, start=1):
                if rt.stopRequested:
                    qfile.status = "STOPPED"
                    qMgr.rev += 1
                    continue

                qfile.status = "RUNNING"
                qMgr.rev += 1
                rt.idx = idx
                rt.currentFile = qfile.name
                rt.step = 0
                rt.steps = snap["steps"]

                def stepCb(s: int, tot: int, el: float) -> None:
                    rt.step = s
                    rt.steps = tot
                    rt.stepRate = s / max(el, 1e-4)
                    pct = s / max(tot, 1)
                    rt.eta = (el / pct - el) if pct > 0 else 0.0

                def ctrlCb() -> str:
                    if rt.stopRequested:
                        return "STOP"
                    if batch.state != "RUNNING":
                        batch.state = "RUNNING"
                        qMgr.rev += 1
                    return "RUN"

                try:
                    tFile = time.time()
                    outExt = ".png" if snap["convertPng"] else qfile.ext
                    outBytes, w, h, psnr, shift = engine.processImage(
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
                        emulateDebug=rt.emulateExecution,
                        guidancePrompt=snap["guidancePrompt"],
                        geoAnchorLow=snap["geoAnchorLow"],
                        geoAnchorHigh=snap["geoAnchorHigh"],
                        temporalWeight=snap["temporalWeight"],
                        maskAugFactor=snap["maskAugFactor"],
                    )
                    stem = Path(sanitizeFilename(qfile.name)).stem
                    if qfile.outPath:
                        oldOut = Path(qfile.outPath)
                        if oldOut.suffix.lower() == outExt.lower():
                            outPath = oldOut
                        else:
                            outPath = batch.exportDir / f"{stem}_lumiya{outExt}"
                    else:
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
                    qMgr.rev += 1

                    dtFile = time.time() - tFile
                    TermLog.emit(
                        f"Exported {TermLog.GREEN}\"{outPath.name}\"{TermLog.RESET} ({w}x{h}, {psnr:.1f}dB) in {dtFile:.2f}s",
                        "ioHandler.py",
                        "OK",
                    )

                    rt.history.insert(
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
                    rt.saveHistory()
                except InterruptedError:
                    qfile.status = "STOPPED"
                    batch.state = "STOPPED"
                    qMgr.rev += 1
                    break
                except Exception as exc:
                    qfile.status = "FAILED"
                    qfile.errorMsg = str(exc)
                    errCount += 1
                    qMgr.rev += 1
                    TermLog.emit(f"Error processing {qfile.name}: {exc}", "worker.py", "ERROR")

            if rt.stopRequested or batch.state == "STOPPED":
                batch.state = "STOPPED"
            elif doneCount == 0 and errCount > 0:
                batch.state = "FAILED"
            else:
                batch.state = "COMPLETED"
            qMgr.rev += 1

            algoMgr.rev += 1
            CFG.save(CONFIG_FILE)
        finally:
            try:
                cleanMemoryAndStorage(ROOT_DIR, RESULTS_ROOT, qMgr.batches, engine, clearRawBytes=False)
            except Exception:
                pass
            rt.busy = False
            rt.paused = False
            rt.stopRequested = False
            rt.activeBatch = "-"
            rt.currentFile = "Idle"
            rt.step = 0
            rt.eta = 0.0
            rt.stepRate = 0.0
            workerLock.release()

    class RequestHandler(BaseHTTPRequestHandler):
        def handle(self) -> None:
            try:
                super().handle()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)

            if parsed.path.startswith("/api/") and not isTrustedRequest(
                self.headers.get("Host"), self.headers.get("Origin"), actualPort
            ):
                self.send_error(HTTPStatus.FORBIDDEN)
                return

            if parsed.path == "/":
                body = UI_FILE.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif parsed.path in (
                "/lumiya_blk.ico",
                "/lumiya_t.ico",
                "/logo.png",
                "/identity/lumiya_blk.ico",
                "/identity/lumiya_t.ico",
                "/identity/logo.png",
            ):
                assetName = Path(parsed.path).name
                assetPath = IDENTITY_DIR / assetName
                if not assetPath.exists() and (ROOT_DIR / assetName).exists():
                    assetPath = ROOT_DIR / assetName
                if not assetPath.exists() and (ROOT_DIR / "assets" / assetName).exists():
                    assetPath = ROOT_DIR / "assets" / assetName
                if assetPath.exists():
                    verifyBrandAssets(ROOT_DIR)
                    data = assetPath.read_bytes()
                    mime = "image/png" if assetName.endswith(".png") else "image/x-icon"
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", mime)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
            elif parsed.path == "/api/stream":
                nonlocal activeSseCount
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                with sseLock:
                    activeSseCount += 1
                sentAlgoRev = -1
                sentBatchRev = -1
                try:
                    while True:
                        majorReady = engine.majorDepsReady or rt.emulateExecution
                        curAlgoRev = algoMgr.rev
                        curBatchRev = qMgr.rev
                        payload: Dict[str, Any] = {
                            "appName": APP_NAME,
                            "appVersion": APP_VERSION,
                            "resultsRoot": str(RESULTS_ROOT),
                            "brandIntegrity": BRAND_STATUS,
                            "hw": mon.read().__dict__,
                            "cfg": CFG.snapshotForStream(),
                            "deps": DEPS_STATUS,
                            "majorReady": majorReady,
                            "ui": {
                                "busy": rt.busy,
                                "paused": rt.paused,
                                "debugMode": rt.debugMode,
                                "emulateExecution": rt.emulateExecution,
                                "activeBatch": rt.activeBatch,
                                "file": rt.currentFile,
                                "idx": rt.idx,
                                "total": rt.total,
                                "step": rt.step,
                                "steps": rt.steps,
                                "eta": rt.eta,
                                "stepRate": rt.stepRate,
                                "history": list(rt.history[:40]),
                            },
                        }
                        if curAlgoRev != sentAlgoRev:
                            payload["algos"] = algoMgr.listMetadata()
                            sentAlgoRev = curAlgoRev
                        if curBatchRev != sentBatchRev:
                            payload["batches"] = qMgr.serializeTree()
                            sentBatchRev = curBatchRev
                        self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode("utf-8"))
                        self.wfile.flush()
                        time.sleep(max(0.25, CFG.pollMs / 1000.0))
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    with sseLock:
                        activeSseCount = max(0, activeSseCount - 1)
                        nowZero = activeSseCount == 0
                    if nowZero:
                        threading.Thread(target=triggerLastTabPurge, daemon=True).start()
            elif parsed.path == "/api/preview_image":
                bid = qs.get("batch", [""])[0]
                fid = qs.get("file", [""])[0]
                preferExport = qs.get("export", ["0"])[0] == "1"
                found = qMgr.getFileBytes(bid, fid, preferExport=preferExport)
                if not found:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                imgBytes, mime = found
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", mime)
                self.send_header("Cache-Control", "no-store, max-age=0")
                self.send_header("Content-Length", str(len(imgBytes)))
                self.end_headers()
                self.wfile.write(imgBytes)
            elif parsed.path == "/api/check_stego":
                bid = qs.get("batch", [""])[0]
                fid = qs.get("file", [""])[0]
                found = qMgr.getFileBytes(bid, fid, preferExport=True)
                if not found:
                    self.sendJson({"ok": False, "found": False, "error": "Processed file not found on disk or memory."})
                    return
                imgBytes, _ = found
                res = inspectStego(imgBytes)
                self.sendJson({"ok": True, **res})
            elif parsed.path == "/api/manifest":
                manifestPath = MANIFEST_FILE if MANIFEST_FILE.exists() else (ROOT_DIR / "install_manifest.log")
                text = manifestPath.read_text(encoding="utf-8") if manifestPath.exists() else "No user/install_manifest.log found."
                self.sendJson({"manifest": text})
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            if not isTrustedRequest(self.headers.get("Host"), self.headers.get("Origin"), actualPort):
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            length = safeInt(self.headers.get("Content-Length", "0"), 0, 0, 200_000_000)
            rawBody = self.rfile.read(length) if length > 0 else b""

            if parsed.path == "/api/create_batch":
                b = qMgr.createOrGetStagingBatch()
                self.sendJson({"batchId": b.batchId})

            elif parsed.path == "/api/upload":
                bid = qs.get("batch", [""])[0]
                fname = qs.get("name", ["upload.jpg"])[0]
                res = qMgr.addFile(bid, fname, rawBody)
                self.sendJson(res)

            elif parsed.path == "/api/check_stego_raw":
                res = inspectStego(rawBody)
                self.sendJson({"ok": True, **res})

            elif parsed.path == "/api/stego_prepare":
                try:
                    mark, compressed = prepareMark(rawBody)
                    self.sendJson({"ok": True, "mark": mark, "compressed": compressed})
                except MarkError as exc:
                    self.sendJson({"ok": False, "error": str(exc)})
                except (OSError, ValueError):
                    self.sendJson({"ok": False, "error": "This file could not be read as an image."})

            elif parsed.path == "/api/open_result":
                name = qs.get("batch", [""])[0]
                folder = RESULTS_ROOT / name
                if not name or folder.resolve().parent != RESULTS_ROOT.resolve() or not folder.is_dir():
                    self.sendJson({"ok": False})
                    return
                openPathForeground(folder)
                self.sendJson({"ok": True})

            elif parsed.path == "/api/batch_action":
                info = parseJsonBody(rawBody)
                act = info.get("action", "")
                bid = info.get("batchId", "")
                b = qMgr.batches.get(bid)

                if act == "run" and not rt.busy and b and (engine.majorDepsReady or rt.emulateExecution or b.stegoMode == "only"):
                    okCfg, errCfg = validateBatchConfig(b, algoMgr, requireFiles=True)
                    if not okCfg:
                        self.sendJson({"ok": False, "error": errCfg})
                        return
                    threading.Thread(target=executeBatch, args=(bid,), daemon=True).start()
                    self.sendJson({"ok": True})
                elif act == "stop" and rt.busy and rt.activeBatch == bid:
                    rt.stopRequested = True
                    self.sendJson({"ok": True})
                elif act == "restart" and not rt.busy and b:
                    okCfg, errCfg = validateBatchConfig(b, algoMgr, requireFiles=True)
                    if not okCfg:
                        self.sendJson({"ok": False, "error": errCfg})
                        return
                    if any(f.valid and not f.rawBytes for f in b.files):
                        self.sendJson(
                            {"ok": False, "error": "Originals were released from memory. Add the photos again to redo this batch."}
                        )
                        return
                    for f in b.files:
                        if f.valid:
                            f.status = "STAGED"
                            f.hasStego = False
                    b.state = "STAGED"
                    qMgr.rev += 1
                    threading.Thread(target=executeBatch, args=(bid,), daemon=True).start()
                    self.sendJson({"ok": True})
                elif act == "update_params" and b and b.state != "RUNNING":
                    if "epsilon" in info:
                        b.epsilon = safeFloat(info["epsilon"], b.epsilon, 1.0, 32.0)
                    if "steps" in info:
                        b.steps = safeInt(info["steps"], b.steps, 10, MAX_STEPS)
                    if safeFloat(info.get("computeLevel", 0), 0.0) in (0.25, 0.5, 1.0, 2.0):
                        b.computeLevel = float(info["computeLevel"])
                    if "seed" in info:
                        b.seed = safeInt(info["seed"], b.seed, 0, 2_147_483_647)
                    if "convertPng" in info:
                        b.convertPng = bool(info["convertPng"])
                    if "stegoStrength" in info:
                        b.stegoStrength = safeFloat(info["stegoStrength"], b.stegoStrength, 1.0, 16.0)
                    if "stegoScale" in info:
                        b.stegoScale = safeFloat(info["stegoScale"], b.stegoScale, 5.0, 100.0)
                    if info.get("stegoPlacement") in PLACEMENTS:
                        b.stegoPlacement = str(info["stegoPlacement"])
                    if info.get("stegoPayload") in ("text", "binary", "image"):
                        b.stegoPayload = str(info["stegoPayload"])
                    if "stegoMark" in info:
                        b.stegoMark = str(info["stegoMark"])
                    if "guidancePrompt" in info:
                        b.guidancePrompt = str(info["guidancePrompt"])
                    if "geoAnchorLow" in info:
                        b.geoAnchorLow = safeFloat(info["geoAnchorLow"], b.geoAnchorLow, 1.0, 8.0)
                    if "geoAnchorHigh" in info:
                        b.geoAnchorHigh = safeFloat(info["geoAnchorHigh"], b.geoAnchorHigh, 1.1, 10.0)
                    if "temporalWeight" in info:
                        b.temporalWeight = safeFloat(info["temporalWeight"], b.temporalWeight, 0.0, 1.0)
                    if "maskAugFactor" in info:
                        b.maskAugFactor = safeFloat(info["maskAugFactor"], b.maskAugFactor, 0.2, 2.0)
                    if "stegoMode" in info and str(info["stegoMode"]) in ("off", "combined", "only"):
                        b.stegoMode = str(info["stegoMode"])
                    if "stegoText" in info:
                        b.stegoText = str(info["stegoText"])
                    if "layers" in info and isinstance(info["layers"], dict):
                        b.layers = {str(k): bool(v) for k, v in info["layers"].items()}
                    qMgr.rev += 1
                    okCfg, errCfg = validateBatchConfig(b, algoMgr, requireFiles=False)
                    self.sendJson({"ok": okCfg, "error": errCfg})
                elif act == "reorder_file":
                    res = qMgr.reorderOrSplitFile(
                        srcBatchId=bid,
                        fileId=str(info.get("fileId", "")),
                        targetBatchId=str(info.get("targetBatchId", bid)),
                        targetIndex=safeInt(info.get("targetIndex", 0), 0),
                    )
                    self.sendJson(res)
                elif act == "open_batch_export" and b:
                    if b.exportDir.exists():
                        openPathForeground(b.exportDir)
                    self.sendJson({"ok": True})
                elif act == "delete_batch":
                    if rt.busy and rt.activeBatch == bid:
                        rt.stopRequested = True
                        time.sleep(0.4)
                    keepExp = bool(info.get("keepExports"))
                    qMgr.deleteBatch(bid, keepExports=keepExp)
                    if not keepExp:
                        rt.removeBatchHistory(bid)
                    self.sendJson({"ok": True})
                elif act == "remove_file":
                    fid = str(info.get("fileId", ""))
                    res = qMgr.removeFile(bid, fid)
                    self.sendJson(res)
                else:
                    self.sendJson({"ok": False})

            elif parsed.path == "/api/clear_history":
                rt.history.clear()
                rt.saveHistory()
                self.sendJson({"ok": True})

            elif parsed.path == "/api/debug_action":
                if not rt.debugMode:
                    self.sendJson({"ok": False, "error": "Debug mode is only available via debug.bat (--debug)."})
                    return
                info = parseJsonBody(rawBody)
                cmd = info.get("cmd", "")
                if cmd == "toggle_emulate":
                    rt.emulateExecution = not rt.emulateExecution
                elif cmd == "mock_deps":
                    stateVal = bool(info.get("state", True))
                    for k in ("torch", "cuda", "diffusers", "transformers", "pil", "psutil"):
                        DEPS_STATUS[k] = stateVal
                    DEPS_STATUS["psutil"] = stateVal and psutil is not None
                    DEPS_STATUS["pil"] = stateVal and Image is not None
                elif cmd == "sim_thermal":
                    mon.debugOverride["tempState"] = info.get("state", "normal")
                    mon.debugOverride["tempC"] = safeFloat(info.get("tempC", 50.0), 50.0)
                elif cmd == "inject_sample":
                    b = qMgr.createOrGetStagingBatch()
                    if DEPS_STATUS["pil"]:
                        im = Image.new("RGB", (640, 480), color=(32, 64, 128))
                        buf = io.BytesIO()
                        im.save(buf, format="JPEG", quality=92)
                        sampleBytes = buf.getvalue()
                    else:
                        sampleBytes = b"\xff\xd8\xff\xe0" + os.urandom(2048)
                    qMgr.addFile(b.batchId, f"DebugSample_{int(time.time()) % 10000}.jpg", sampleBytes)
                self.sendJson({"ok": True})

            elif parsed.path == "/api/algo_action":
                info = parseJsonBody(rawBody)
                if info.get("action") == "delete":
                    res = algoMgr.deleteCustomAlgo(str(info.get("algoId", "")))
                    self.sendJson({**res, "algos": algoMgr.listMetadata()})
                else:
                    self.sendJson({"ok": False})

            elif parsed.path == "/api/save_config":
                newCfg = parseJsonBody(rawBody)
                CFG.applyDict(newCfg)
                CFG.save(CONFIG_FILE)
                if "overrideHardware" in newCfg or "protectionMode" in newCfg:
                    algoMgr.rev += 1
                self.sendJson({"ok": True})

            elif parsed.path == "/api/rescan_algos":
                algos = algoMgr.scanAlgos()
                self.sendJson({"ok": True, "algos": algos})

            elif parsed.path == "/api/system_maint":
                cmdType = qs.get("cmd", [""])[0]
                if cmdType == "install":
                    if sys.platform == "win32":
                        subprocess.Popen(["cmd.exe", "/c", "start", "PORTtralica Installer", "cmd.exe", "/k", str(ROOT_DIR / "install.bat")])
                    else:
                        shPath = str(ROOT_DIR / "run.sh")
                        term = shutil.which("x-terminal-emulator") or shutil.which("gnome-terminal") or shutil.which("konsole") or shutil.which("xfce4-terminal") or shutil.which("xterm")
                        cmd = ["bash", "-c", f"bash '{shPath}' --install; echo; read -n 1 -s -r -p 'Press any key to close...';"]
                        if term and "gnome-terminal" in Path(term).name:
                            subprocess.Popen([term, "--"] + cmd)
                        elif term:
                            subprocess.Popen([term, "-e"] + cmd)
                        else:
                            subprocess.Popen(["bash", shPath, "--install"])
                    self.sendJson({"ok": True})
                elif cmdType == "run_cleaner":
                    rep = cleanMemoryAndStorage(ROOT_DIR, RESULTS_ROOT, qMgr.batches, engine)
                    self.sendJson({"ok": True, "report": rep})
                elif cmdType == "tab_closed":
                    with sseLock:
                        noTabs = activeSseCount <= 1
                    if noTabs and not rt.busy:
                        rep = cleanMemoryAndStorage(ROOT_DIR, RESULTS_ROOT, qMgr.batches, engine, clearRawBytes=True)
                        self.sendJson({"ok": True, "report": rep})
                    else:
                        self.sendJson({"ok": True})
                elif cmdType == "restart_service":
                    if rt.busy:
                        rt.stopRequested = True
                        time.sleep(0.3)
                    cleanMemoryAndStorage(ROOT_DIR, RESULTS_ROOT, qMgr.batches, engine, clearRawBytes=True)
                    self.sendJson({"ok": True, "restarting": True})

                    def performRestart() -> None:
                        time.sleep(0.35)
                        TermLog.emit("Restarting PORTtralica Lumiya service...", "bootstrap.py", "INFO")
                        os._exit(42)

                    threading.Thread(target=performRestart, daemon=True).start()
                elif cmdType == "open_results":
                    openPathForeground(RESULTS_ROOT)
                    self.sendJson({"ok": True})
                elif cmdType == "open_algos":
                    openPathForeground(ALGOS_DIR)
                    self.sendJson({"ok": True})
                else:
                    self.sendJson({"ok": False})
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def sendJson(self, obj: Dict[str, Any]) -> None:
            try:
                raw = json.dumps(obj).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass

    class QuietThreadingHTTPServer(ThreadingHTTPServer):
        allow_reuse_address = True

        def handle_error(self, request: Any, client_address: Any) -> None:
            _, exc, _ = sys.exc_info()
            if isinstance(exc, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError)):
                return
            super().handle_error(request, client_address)

    server: Optional[QuietThreadingHTTPServer] = None
    maxAttempts = 50
    for offset in range(maxAttempts):
        candidatePort = port + offset
        try:
            server = QuietThreadingHTTPServer(("127.0.0.1", candidatePort), RequestHandler)
            actualPort = candidatePort
            break
        except OSError:
            if offset == 0:
                TermLog.emit(f"Port {port} is occupied. Engaging Automatic Port Selection (APS)...", "server.py", "WARNING")
            continue

    if server is None:
        TermLog.emit(f"Fatal: Could not acquire any socket in range {port}-{port + maxAttempts - 1}", "server.py", "ERROR")
        raise RuntimeError(f"All ports from {port} to {port + maxAttempts - 1} are occupied.")

    if actualPort != port:
        TermLog.emit(
            f"APS Socket Fallback: Listening on port {TermLog.CYAN}{actualPort}{TermLog.RESET} (preferred {port} was busy)",
            "server.py",
            "INFO",
        )

    url = f"http://127.0.0.1:{actualPort}"
    TermLog.emit(f"WebUI listening on {TermLog.GREEN}\"{url}\"{TermLog.RESET}", "server.py", "OK")
    print("=" * 96)
    if not noBrowser:
        canOpen = True
        if sys.platform != "win32":
            if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
                canOpen = False
        if canOpen:
            try:
                webbrowser.open(url)
            except Exception:
                pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        cleanMemoryAndStorage(ROOT_DIR, RESULTS_ROOT, qMgr.batches, engine)
        server.server_close()


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
        except Exception as exc:
            realOut.write(f"ERR\t{exc}\n")
            realOut.flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--compute-worker", action="store_true")
    args = parser.parse_args()
    if args.compute_worker:
        runComputeWorker()
    elif args.worker:
        runServer(port=args.port, debugMode=args.debug, noBrowser=args.no_browser)
    else:
        targetPort = findAvailablePort(args.port)
        firstLaunch = not args.no_browser
        while True:
            cmd = [sys.executable, str(Path(__file__).resolve()), "--worker", "--port", str(targetPort)]
            if args.debug:
                cmd.append("--debug")
            if not firstLaunch:
                cmd.append("--no-browser")
            childProc = subprocess.Popen(cmd, cwd=str(ROOT_DIR))
            try:
                rc = childProc.wait()
            except KeyboardInterrupt:
                childProc.kill()
                break
            firstLaunch = False
            if rc != 42:
                break
            time.sleep(0.25)
