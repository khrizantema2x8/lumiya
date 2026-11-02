from __future__ import annotations

import argparse
import ast
import base64
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
import statistics
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

from cleaner import cleanMemoryAndStorage
from stego.mark import PLACEMENTS, MarkError, embedMark, inspectStego, prepareMark

# The progress bar uses block characters a legacy console codepage cannot encode.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

APP_NAME = "PORTtralica Lumiya"
APP_VERSION = "v0.5.034.4100 (Pilot)"

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
        "conda": "Detected" if (shutil.which("conda") or Path(os.path.expanduser("~/miniconda3")).exists() or Path(os.path.expanduser("~/anaconda3")).exists()) else "Missing",
    },
    "recommended": {
        "python": "3.13.x",
        "torch": "2.15.0 (build matched to driver)",
        "cuda": "Matched to driver",
        "diffusers": "0.42.1",
        "transformers": "5.22.1",
        "pil": ">= 10.3.0",
        "psutil": ">= 5.9.8",
        "git": ">= 2.45.0",
        "conda": "Miniconda3 24.x",
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
    if sys.platform == "win32":
        for p in (
            r"C:\Windows\System32\nvidia-smi.exe",
            r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
        ):
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

    if DEPS_STATUS["torch"]:
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
                timeout=2.0,
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
                DEPS_STATUS["vramGb"] = round(float(memMb) / 1024.0, 2)
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
                    timeout=6.0,
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
            DEPS_STATUS["advisoryReason"] = "No CUDA-accelerable hardware detected. Running this program on non-CUDA accelerated platform will be considerably slower. Consider changing the platform or continue and accept less optimal performance."
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
UI_FILE = ROOT_DIR / "ui.html"
CONFIG_FILE = ROOT_DIR / "config.json"
HISTORY_FILE = ROOT_DIR / "history.json"
MANIFEST_FILE = ROOT_DIR / "install_manifest.log"
MAX_STEPS = 4000
VALID_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff")
DEFAULT_ALGO_IDS = (
    "mirage",
    "veto",
    "diffusionguard",
    "metacloak",
    "mistv2",
    "srim",
    "impress",
    "antipure",
    "promptflare",
    "decontext_cad",
    "anti_i2v",
    "vid_freeze",
    "chronolock",
    "idprotector",
    "fastprotect_tcuap",
    "diffvax",
    "genptw_tagwm",
    "obliviate",
    "photoguard",
    "blurguard",
    "antiInpainting",
)


def openPathForeground(targetPath: Path) -> None:
    """Forces Windows Explorer to open in the foreground above the browser window."""
    targetPath.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        try:
            psCmd = (
                f'$ws = New-Object -ComObject WScript.Shell; '
                f'Start-Process explorer.exe -ArgumentList \'"{str(targetPath.resolve())}"\'; '
                f'Start-Sleep -Milliseconds 250; '
                f'$ws.AppActivate("{targetPath.name}")'
            )
            subprocess.Popen(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", psCmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except Exception:
            subprocess.Popen(["explorer.exe", str(targetPath.resolve())])


def atomicWrite(path: Path, text: str) -> None:
    """Writes via a sibling file so a crash mid-save cannot leave a truncated file."""
    tmpPath = path.with_name(f"{path.name}.{threading.get_ident()}.partial")
    tmpPath.write_text(text, encoding="utf-8")
    os.replace(tmpPath, path)


@dataclass
class SuiteConfig:
    computeBackend: str = "auto"
    epsilon: float = 4.0
    computeLevel: float = 1.0
    seed: int = 0
    steps: int = 50
    guidancePrompt: str = ""
    geoAnchorLow: float = 1.7
    geoAnchorHigh: float = 7.1
    temporalWeight: float = 0.50
    maskAugFactor: float = 1.00
    workingDim: int = 768
    precision: str = "fp16"
    reserveVramMb: int = 600
    jpegQuality: int = 98
    preserveExif: bool = True
    preserveIcc: bool = True
    pollMs: int = 1000
    tempWarnC: float = 62.0
    tempCritC: float = 85.0
    tempErraticDelta: float = 12.0
    loadWarnPct: float = 85.0
    overrideHardware: bool = False
    stegoMode: str = "off"
    stegoText: str = "PORTtralica Lumiya - Protected Asset"
    stegoPayload: str = "text"
    stegoStrength: float = 4.0
    stegoScale: float = 40.0
    stegoPlacement: str = "center"
    stegoMark: str = ""
    favoriteAlgos: List[str] = field(default_factory=lambda: ["photoguard"])
    algoLastUsed: Dict[str, str] = field(default_factory=dict)
    layers: Dict[str, bool] = field(default_factory=lambda: {k: k == "photoguard" for k in DEFAULT_ALGO_IDS})

    def save(self) -> None:
        atomicWrite(CONFIG_FILE, json.dumps(self.__dict__, indent=2))

    @classmethod
    def load(cls) -> "SuiteConfig":
        cfg = cls()
        if CONFIG_FILE.exists():
            try:
                raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                for key, val in raw.items():
                    if hasattr(cfg, key):
                        setattr(cfg, key, val)
                cfg.steps = min(MAX_STEPS, max(15, int(cfg.steps)))
            except Exception:
                pass
        return cfg


CFG = SuiteConfig.load()


def workingSizes(width: int, height: int, vramGb: float) -> List[Tuple[int, int]]:
    """Editor input sizes to protect against: geometric grid from 0.25 MP to a VRAM-capped top (spec 10.2)."""
    # shortcut: top anchor capped at 0.6 MP under 8 GB VRAM, editors above that are less covered; raise with remote compute.
    topMp = min(4.2, 0.6 if vramGb < 8.0 else 1.0)
    pixels = width * height
    sizes = []
    mp = 0.25
    while True:
        scale = min(1.0, math.sqrt(mp * 1e6 / pixels))
        size = (max(8, round(height * scale / 8) * 8), max(8, round(width * scale / 8) * 8))
        if size not in sizes:
            sizes.append(size)
        if mp >= topMp:
            return sizes
        mp = min(topMp, mp * 1.96)


def hardwareBlockReason(meta: Dict[str, Any]) -> str:
    """Compares the ALGO_META hardware block with the startup hardware scan."""
    hardware = meta.get("hardware", {})
    if hardware.get("requiresCuda") and not DEPS_STATUS["cuda"]:
        return "Requires an NVIDIA CUDA GPU; none was found."
    minVram = float(hardware.get("minVramGb", 0))
    if DEPS_STATUS["cuda"] and minVram > float(DEPS_STATUS["vramGb"]):
        return f"Requires {minVram:g} GB VRAM; this system has {DEPS_STATUS['vramGb']:g} GB."
    return ""


class AlgoPluginManager:
    """Discovers pre-packaged algorithms in algos/ without importing heavy modules at startup."""

    def __init__(self, algosRoot: Path) -> None:
        self.root = algosRoot
        self.root.mkdir(parents=True, exist_ok=True)
        self.plugins: Dict[str, Dict[str, Any]] = {}
        self.rev: int = 0
        self.scanAlgos()

    @staticmethod
    def extractAstMeta(pyCode: str, fallbackId: str) -> Dict[str, str]:
        """Safely extracts ALGO_META via AST without executing plugin imports at boot."""
        try:
            tree = ast.parse(pyCode)
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id in ("ALGO_META", "algoMeta"):
                            val = ast.literal_eval(node.value)
                            if isinstance(val, dict):
                                return val
        except Exception:
            pass
        return {"id": fallbackId, "name": fallbackId}

    def getPluginModule(self, algoId: str) -> Optional[Any]:
        """Lazily imports and caches a plugin module only when an active defense batch executes."""
        plugin = self.plugins.get(algoId)
        if not plugin:
            return None
        if plugin.get("module") is not None:
            return plugin["module"]
        try:
            pyPath = plugin["pyPath"]
            spec = importlib.util.spec_from_file_location(f"algos.{plugin['folderName']}", pyPath)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                plugin["module"] = mod
                return mod
        except Exception as exc:
            TermLog.emit(f"Lazy import failed for {algoId}: {exc}", "algoLoader.py", "ERROR")
        return None

    def deleteCustomAlgo(self, algoId: str) -> Dict[str, Any]:
        if algoId in DEFAULT_ALGO_IDS:
            return {"ok": False, "error": "Default built-in algorithms cannot be deleted."}
        plugin = self.plugins.get(algoId)
        if not plugin:
            return {"ok": False, "error": "Algorithm not found."}
        folder = Path(plugin["folderPath"])
        if folder.exists() and folder.parent.resolve() == self.root.resolve():
            shutil.rmtree(folder, ignore_errors=True)
            TermLog.emit(f"Deleted custom algorithm folder {TermLog.YELLOW}{folder.name}{TermLog.RESET}", "algoLoader.py", "INFO")
        self.scanAlgos()
        return {"ok": True}

    def scanAlgos(self) -> List[Dict[str, Any]]:
        self.plugins.clear()
        for subDir in sorted(self.root.iterdir()):
            if not subDir.is_dir() or subDir.name.startswith("_") or subDir.name.startswith("."):
                continue
            pyFiles = sorted(subDir.glob("*.py"))
            if not pyFiles:
                continue
            pyPath = pyFiles[0]
            mdFile = subDir / "readmyalgo.md"
            try:
                pyCode = pyPath.read_text(encoding="utf-8", errors="replace")
                meta = self.extractAstMeta(pyCode, subDir.name)

                algoId = meta.get("id", subDir.name)
                shortInfo = meta.get("shortInfo", "Modular defense layer.")
                hasMd = mdFile.exists() and mdFile.stat().st_size > 0
                mdText = mdFile.read_text(encoding="utf-8", errors="replace") if hasMd else ""

                self.plugins[algoId] = {
                    "id": algoId,
                    "name": meta.get("name", subDir.name),
                    "attribution": meta.get("attribution", "Custom Algorithm Plugin"),
                    "shortInfo": shortInfo,
                    "paperUrl": meta.get("paperUrl", "https://arxiv.org/"),
                    "lastUsed": CFG.algoLastUsed.get(algoId, "Never"),
                    "paper": meta.get("paper"),
                    "hardware": meta.get("hardware", {}),
                    "params": meta.get("params", []),
                    "notRebuilt": not meta.get("paper"),
                    "hardwareReason": hardwareBlockReason(meta),
                    "isDefault": algoId in DEFAULT_ALGO_IDS or subDir.name in DEFAULT_ALGO_IDS,
                    "folderName": subDir.name,
                    "folderPath": str(subDir.resolve()),
                    "pyFilename": pyPath.name,
                    "pyPath": str(pyPath.resolve()),
                    "pyCode": pyCode,
                    "hasReadme": hasMd,
                    "mdFilename": mdFile.name if hasMd else "readmyalgo.md (Missing)",
                    "mdPath": str(mdFile.resolve()),
                    "readmeMd": mdText,
                    "module": None,
                }
                if algoId not in CFG.layers:
                    CFG.layers[algoId] = False
            except Exception as exc:
                TermLog.emit(f"Failed scanning algo plugin {subDir.name}: {exc}", "algoLoader.py", "ERROR")
        self.rev += 1
        return self.listMetadata()

    @staticmethod
    def blockReason(plugin: Dict[str, Any]) -> str:
        return "" if CFG.overrideHardware else AlgoPluginManager.limitReason(plugin)

    @staticmethod
    def limitReason(plugin: Dict[str, Any]) -> str:
        return " ".join(filter(None, (plugin["hardwareReason"], "Not rebuilt yet." if plugin["notRebuilt"] else "")))

    def listMetadata(self) -> List[Dict[str, Any]]:
        for k, item in self.plugins.items():
            item["lastUsed"] = CFG.algoLastUsed.get(k, "Never")
            item["limitReason"] = self.limitReason(item)
            item["cannotRunReason"] = self.blockReason(item)
            item["cannotRun"] = bool(item["cannotRunReason"])
        return [{k: v for k, v in item.items() if k != "module"} for item in self.plugins.values()]


class _NvmlUtilization(ctypes.Structure):
    _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]


class _NvmlMemory(ctypes.Structure):
    _fields_ = [
        ("total", ctypes.c_ulonglong),
        ("free", ctypes.c_ulonglong),
        ("used", ctypes.c_ulonglong),
    ]


@dataclass
class SensorSnapshot:
    cpu: float = 0.0
    ram: float = 0.0
    gpuName: str = "CPU"
    gpu: float = 0.0
    vramUsed: float = 0.0
    vramTotal: float = 0.0
    vramFreeMb: float = 0.0
    tempC: float = 0.0
    tempF: float = 32.0
    tempSensorLabel: str = "CPU TEMP"
    tempState: str = "normal"
    powerW: float = 0.0


class TelemetryMonitor:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.snap = SensorSnapshot()
        self.tempWindow: List[float] = []
        self.rawTemps: List[float] = []
        self.debugOverride: Dict[str, Any] = {}
        self.hasCuda = DEPS_STATUS["cuda"]
        rawGpu = DEPS_STATUS["gpuName"] if self.hasCuda else "CPU"
        self.gpuName = (
            rawGpu.replace("NVIDIA ", "")
            .replace("GeForce ", "")
            .replace("Laptop GPU", "Mobile")
            .strip()
        )
        self._nvmlLib: Any = None
        self._nvmlHandle: Any = None
        self._lastSmiTime: float = 0.0
        self._cachedHw: Tuple[float, float, float, float, str, float] = (
            0.0,
            0.0,
            0.0,
            float(DEPS_STATUS.get("vramGb", 0.0)),
            "GPU TEMP" if self.hasCuda else "CPU TEMP",
            0.0,
        )
        self._initNvml()
        threading.Thread(target=self.pollLoop, daemon=True).start()

    def _initNvml(self) -> None:
        """Loads NVML in-process via ctypes to eliminate per-second nvidia-smi.exe subprocess overhead."""
        candidates = (
            ["nvml.dll", r"C:\Windows\System32\nvml.dll", r"C:\Program Files\NVIDIA Corporation\NVSMI\nvml.dll"]
            if sys.platform == "win32"
            else ["libnvidia-ml.so.1", "libnvidia-ml.so"]
        )
        for pathStr in candidates:
            try:
                lib = ctypes.WinDLL(pathStr) if sys.platform == "win32" else ctypes.CDLL(pathStr)
                if lib.nvmlInit_v2() == 0:
                    handle = ctypes.c_void_p()
                    if lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(handle)) == 0:
                        self._nvmlLib = lib
                        self._nvmlHandle = handle
                        return
            except Exception:
                continue

    def read(self) -> SensorSnapshot:
        with self.lock:
            return SensorSnapshot(**self.snap.__dict__)

    def queryHardwareMetrics(self) -> Tuple[float, float, float, float, str, float]:
        if self._nvmlLib is not None and self._nvmlHandle is not None:
            try:
                util = _NvmlUtilization()
                gpuUtil = 0.0
                if self._nvmlLib.nvmlDeviceGetUtilizationRates(self._nvmlHandle, ctypes.byref(util)) == 0:
                    gpuUtil = float(util.gpu)

                tempVal = ctypes.c_uint(0)
                tempC = 0.0
                if self._nvmlLib.nvmlDeviceGetTemperature(self._nvmlHandle, 0, ctypes.byref(tempVal)) == 0:
                    tempC = float(tempVal.value)

                memInfo = _NvmlMemory()
                memU, memT = 0.0, float(DEPS_STATUS.get("vramGb", 0.0))
                if self._nvmlLib.nvmlDeviceGetMemoryInfo(self._nvmlHandle, ctypes.byref(memInfo)) == 0:
                    memU = float(memInfo.used) / (1024.0 ** 3)
                    memT = float(memInfo.total) / (1024.0 ** 3)

                pwrMilli = ctypes.c_uint(0)
                gpuPower = 0.0
                if self._nvmlLib.nvmlDeviceGetPowerUsage(self._nvmlHandle, ctypes.byref(pwrMilli)) == 0:
                    gpuPower = float(pwrMilli.value) / 1000.0

                self._cachedHw = (gpuUtil, tempC, memU, memT, "GPU TEMP", gpuPower)
                return self._cachedHw
            except Exception:
                pass

        now = time.time()
        if now - self._lastSmiTime < 4.0:
            return self._cachedHw
        self._lastSmiTime = now

        try:
            cmd = [
                NVIDIA_SMI_BIN,
                "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total,power.draw",
                "--format=csv,noheader,nounits",
            ]
            startupInfo = None
            if sys.platform == "win32":
                startupInfo = subprocess.STARTUPINFO()
                startupInfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            out = subprocess.check_output(
                cmd, startupinfo=startupInfo, stderr=subprocess.DEVNULL, timeout=1.0
            ).decode("utf-8").strip()
            parts = [x.strip() for x in out.splitlines()[0].split(",")]
            gpuUtil = float(parts[0])
            tempC = float(parts[1])
            memU = float(parts[2]) / 1024.0
            memT = float(parts[3]) / 1024.0
            try:
                gpuPower = float(parts[4]) if len(parts) > 4 else 0.0
            except Exception:
                gpuPower = 0.0
            self._cachedHw = (gpuUtil, tempC, memU, memT, "GPU TEMP", gpuPower)
            return self._cachedHw
        except Exception:
            cpuTemp = 0.0
            if DEPS_STATUS["psutil"] and hasattr(psutil, "sensors_temperatures"):
                try:
                    temps = psutil.sensors_temperatures()
                    for entries in temps.values():
                        if entries:
                            cpuTemp = float(entries[0].current)
                            break
                except Exception:
                    pass
            if DEPS_STATUS["cuda"]:
                vramU = 0.0
                if "torch" in sys.modules:
                    try:
                        vramU = float(sys.modules["torch"].cuda.memory_reserved(0)) / (1024.0 ** 3)
                    except Exception:
                        pass
                self._cachedHw = (0.0, cpuTemp, vramU, float(DEPS_STATUS.get("vramGb", 0.0)), "GPU TEMP", 0.0)
                return self._cachedHw
            self._cachedHw = (0.0, cpuTemp, 0.0, 0.0, "CPU TEMP", 0.0)
            return self._cachedHw

    def smoothTemp(self, tempC: float) -> float:
        """Median of recent readings: mobile GPUs report 1-2 second idle spikes of 10+ degrees."""
        if tempC <= 0:
            return tempC
        self.rawTemps = (self.rawTemps + [tempC])[-5:]
        return statistics.median(self.rawTemps)

    def evaluateThermalState(self, tempC: float) -> str:
        if "tempState" in self.debugOverride:
            return str(self.debugOverride["tempState"])
        if tempC <= 0:
            return "normal"
        self.tempWindow.append(tempC)
        if len(self.tempWindow) > 8:
            self.tempWindow.pop(0)

        if len(self.tempWindow) >= 4:
            deltas = [
                abs(self.tempWindow[i] - self.tempWindow[i - 1])
                for i in range(1, len(self.tempWindow))
            ]
            if sum(1 for d in deltas if d >= CFG.tempErraticDelta) >= 2:
                return "erratic"

            recent = self.tempWindow[-4:]
            if all(t > CFG.tempCritC for t in recent):
                return "crit"
            if all(t > CFG.tempWarnC for t in recent):
                return "warn"
        return "normal"

    def pollLoop(self) -> None:
        if DEPS_STATUS["psutil"]:
            psutil.cpu_percent(interval=None)
        while True:
            cpu = psutil.cpu_percent(interval=None) if DEPS_STATUS["psutil"] else 0.0
            ram = psutil.virtual_memory().percent if DEPS_STATUS["psutil"] else 0.0
            gpu, tempC, vramU, vramT, sensorLbl, gpuPowerW = self.queryHardwareMetrics()
            tempC = self.smoothTemp(tempC)

            if "tempC" in self.debugOverride:
                tempC = float(self.debugOverride["tempC"])
            if "gpu" in self.debugOverride:
                gpu = float(self.debugOverride["gpu"])

            tempF = (tempC * 9.0 / 5.0) + 32.0 if tempC > 0 else 0.0
            freeMb = max(0.0, (vramT - vramU) * 1024.0)
            tState = self.evaluateThermalState(tempC)
            sysPowerW = round(14.0 + (cpu * 0.42) + (gpuPowerW if gpuPowerW > 0.5 else (gpu * 0.45)), 1)

            with self.lock:
                self.snap = SensorSnapshot(
                    cpu=cpu,
                    ram=ram,
                    gpuName=self.gpuName,
                    gpu=gpu,
                    vramUsed=vramU,
                    vramTotal=vramT,
                    vramFreeMb=freeMb,
                    tempC=tempC,
                    tempF=tempF,
                    tempSensorLabel=sensorLbl,
                    tempState=tState,
                    powerW=sysPowerW,
                )
            time.sleep(max(0.25, CFG.pollMs / 1000.0))


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
    stegoMode: str = field(default_factory=lambda: CFG.stegoMode)
    stegoText: str = field(default_factory=lambda: CFG.stegoText)
    stegoStrength: float = field(default_factory=lambda: CFG.stegoStrength)
    stegoScale: float = field(default_factory=lambda: CFG.stegoScale)
    stegoPlacement: str = field(default_factory=lambda: CFG.stegoPlacement)
    stegoPayload: str = field(default_factory=lambda: CFG.stegoPayload)
    stegoMark: str = field(default_factory=lambda: CFG.stegoMark)

    @property
    def stegoTextActive(self) -> str:
        return self.stegoText if self.stegoPayload == "text" else ""

    @property
    def stegoMarkActive(self) -> str:
        return self.stegoMark if self.stegoPayload == "image" else ""
    layers: Dict[str, bool] = field(default_factory=lambda: dict(CFG.layers))
    files: List[QueuedFile] = field(default_factory=list)

    @property
    def exportDir(self) -> Path:
        return RESULTS_ROOT / self.batchId

    @property
    def hasExported(self) -> bool:
        return any(bool(f.outPath) for f in self.files)


def validateBatchConfig(batch: BatchQueue) -> Tuple[bool, str]:
    """Ensures batch parameters and algorithm selections are non-empty before execution or save."""
    if not (1.0 <= float(batch.epsilon) <= 32.0):
        return False, "Budget must be between 1 and 32."
    if not (0.0 <= float(batch.temporalWeight) <= 1.0):
        return False, "Temporal weight must be between 0.0 and 1.0."
    if not (0.2 <= float(batch.maskAugFactor) <= 2.0):
        return False, "Mask augmentation factor must be between 0.2 and 2.0."
    if batch.stegoMode not in ("off", "combined", "only"):
        return False, f"Invalid defense mode '{batch.stegoMode}'."
    if batch.stegoMode != "only":
        if not batch.layers or not any(bool(v) for v in batch.layers.values()):
            return False, "At least one AI-Defense Layers algorithm must be enabled when AI-blocking is active."
    if batch.stegoMode in ("combined", "only") and not str(batch.stegoTextActive or "").strip() and not batch.stegoMarkActive:
        return False, "Add the hidden text or choose a mark image when steganography is enabled."
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
        safeName = Path(filename).name
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
                    mime = "image/png" if f.ext == ".png" else "image/jpeg"
                    if preferExport and f.outPath and Path(f.outPath).exists():
                        return Path(f.outPath).read_bytes(), mime
                    if f.rawBytes:
                        return f.rawBytes, mime
                    if f.outPath and Path(f.outPath).exists():
                        return Path(f.outPath).read_bytes(), mime
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
                out.append(
                    {
                        "batchId": b.batchId,
                        "createdAt": b.createdAt,
                        "state": b.state,
                        "hasExported": b.hasExported,
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
                        "layers": b.layers,
                        "files": [
                            {
                                "fileId": f.fileId,
                                "name": f.name,
                                "dims": f"{f.width}x{f.height}" if f.width else "Invalid",
                                "sizeKb": round(f.sizeBytes / 1024.0, 1),
                                "valid": f.valid,
                                "errorMsg": f.errorMsg,
                                "status": f.status,
                                "hasStego": f.hasStego,
                                "hasExport": bool(f.outPath),
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
    def __init__(self, algoMgr: AlgoPluginManager) -> None:
        self.algoMgr = algoMgr
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
            self.vae = AutoencoderKL.from_pretrained("stabilityai/sd-vae-ft-mse", torch_dtype=dtype).to(device)
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
        """Releases cached VAE weights and intermediate tensors after batch completion to drop idle RAM/VRAM."""
        hadModel = self.vae is not None or bool(self.cache)
        self.vae = None
        self.vaeDevice = None
        self.cache.clear()
        return hadModel

    @staticmethod
    def visibilityMap(xOrig: Any) -> Any:
        """Per-pixel share of the budget: full in detail, small in flat areas, where eyes notice change."""
        luma = (xOrig * torch.tensor([0.299, 0.587, 0.114], device=xOrig.device).view(1, 3, 1, 1)).sum(1, keepdim=True)
        radius = max(4, min(xOrig.shape[-2:]) // 200)
        size = 2 * radius + 1
        mean = F.avg_pool2d(luma, size, 1, radius)
        spread = (F.avg_pool2d(luma ** 2, size, 1, radius) - mean ** 2).clamp(min=0.0).sqrt()
        return F.avg_pool2d((spread / 0.05).clamp(0.12, 1.0), size, 1, radius)

    def grayTarget(self, height: int, width: int, device: str, dtype: Any) -> Any:
        """VAE latent of a mid-gray image, the target of encoder-attack style plugins."""
        key = (height, width, device, str(dtype))
        if key not in self.cache:
            with torch.no_grad():
                gray = torch.zeros(1, 3, height, width, device=device, dtype=dtype)
                self.cache[key] = self.vae.encode(gray).latent_dist.mean.detach().float()
        return self.cache[key]

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
        if hasStego:
            pilImg = embedMark(pilImg, stegoText, stegoOpts or {}, lossless=fileExt.lower() not in (".jpg", ".jpeg"))
        if alpha is not None:
            pilImg.putalpha(alpha)
        outBuf = io.BytesIO()
        saveKw: Dict[str, Any] = {}
        if iccProfile:
            saveKw["icc_profile"] = iccProfile
        ext = fileExt.lower()
        if ext in (".jpg", ".jpeg"):
            if exifBytes:
                saveKw["exif"] = exifBytes
            if hasStego and stegoText.strip():
                saveKw["comment"] = f"[LUMIYA::{stegoText}]".encode("utf-8")
            pilImg.convert("RGB").save(outBuf, format="JPEG", quality=CFG.jpegQuality, subsampling=0, optimize=True, **saveKw)
            markBytes = (stegoOpts or {}).get("mark") if hasStego else None
            if markBytes:
                # JPEG destroys bit planes; a PNG after the end marker is the standard route tools like binwalk extract.
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
                # EXIF is read after the transpose so the Orientation tag cannot rotate the pixels twice.
                exifBytes = transposedIm.getexif().tobytes() if CFG.preserveExif and "exif" in rawIm.info else None
                iccProfile = rawIm.info.get("icc_profile") if CFG.preserveIcc else None
                im = transposedIm.convert("RGB")
                width, height = im.size
                hasStego = stegoMode in ("only", "combined") and bool(stegoText.strip() or (stegoOpts or {}).get("mark"))
                alpha = transposedIm.getchannel("A") if "A" in transposedIm.getbands() else None
                outBytes = self.encodeOutputImage(im, fileExt, hasStego, stegoText, exifBytes, iccProfile, stegoOpts, alpha)
                import numpy as np
                before = np.asarray(im, dtype=np.float64)
                after = np.asarray(Image.open(io.BytesIO(outBytes)).convert("RGB"), dtype=np.float64)
                mse = float(np.mean((after - before) ** 2))
                psnr = 10.0 * math.log10((255.0 ** 2) / max(mse, 1e-10))
                return outBytes, width, height, psnr, float(np.abs(after - before).max())
            return rawBytes, 512, 512, 0.0, 0.0

        device, dtype = self.ensureLoaded()

        rawIm = Image.open(io.BytesIO(rawBytes))
        transposedIm = ImageOps.exif_transpose(rawIm)
        # EXIF is read after the transpose so the Orientation tag cannot rotate the pixels twice.
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
                raise RuntimeError(f"{plugin['name']} is not rebuilt yet, so it cannot run.")
            if enabled and plugin and not self.algoMgr.blockReason(plugin):
                CFG.algoLastUsed[k] = nowStamp
                mod = self.algoMgr.getPluginModule(k)
                if mod is not None:
                    activePlugins.append((mod, plugin["paper"]))
        if not activePlugins:
            raise RuntimeError("None of the selected algorithms can run on this system.")

        budget = float(epsilon255)
        eps = budget / 255.0

        gen = torch.Generator().manual_seed(int(seed))
        xOrig = T.ToTensor()(origRgb).unsqueeze(0).to(device, dtype=torch.float32)
        # Soft limit: tanh has no clipping plateaus, whose edges show as contour lines on smooth skin.
        limitMap = eps * self.visibilityMap(xOrig)
        latent = torch.zeros_like(xOrig, requires_grad=True)
        anchors = workingSizes(origW, origH, float(DEPS_STATUS["vramGb"]))
        ctx: Dict[str, Any] = {"guidancePrompt": guidancePrompt, "generator": gen}
        totalSteps = sum(max(1, round(paper["steps"] * computeLevel)) for _, paper in activePlugins)
        tStart = time.time()
        step = appliedSteps = 0

        for mod, paper in activePlugins:
            pluginSteps = max(1, round(paper["steps"] * computeLevel))
            stepSize = 5.0 / pluginSteps
            lossFn = mod.computeLoss
            transformFn = getattr(mod, "transformInput", None)
            for _ in range(pluginSteps):
                if controlCb() == "STOP":
                    raise InterruptedError("Batch stopped by user.")
                step += 1
                workH, workW = anchors[step % len(anchors)]
                xAdv = torch.clamp(xOrig + limitMap * torch.tanh(latent), 0.0, 1.0)
                # Only this branch is resized: it models the editor; the output stays on the native grid.
                xWork = F.interpolate(xAdv, size=(workH, workW), mode="bilinear", antialias=True) * 2.0 - 1.0
                ctx["zTargetMean"] = self.grayTarget(workH, workW, device, dtype)
                xIn = transformFn(xWork, step, ctx) if transformFn else xWork
                self.validateTensorShape(xIn, 4, "xIn")
                loss = lossFn(self.vae.encode(xIn.to(dtype)).latent_dist, ctx)
                if torch.isfinite(loss):
                    grad = torch.autograd.grad(loss, latent)[0]
                    with torch.no_grad():
                        # Scaled, not sign: the sign of an upsampled gradient has hard edges that read as worm patterns.
                        scale = torch.quantile(grad.abs().flatten()[::97], 0.98).clamp(min=1e-12)
                        latent.sub_(stepSize * (grad / scale).clamp(-1.0, 1.0))
                    appliedSteps += 1
                elapsed = max(time.time() - tStart, 1e-4)
                TermLog.progress(step, totalSteps, elapsed)
                stepCb(step, totalSteps, elapsed)

        if appliedSteps == 0:
            raise RuntimeError("No optimization step produced a valid loss; image was not protected.")

        import numpy as np
        # Dithered rounding: plain rounding turns a smooth layer into visible bands of equal value.
        limit = math.floor(budget)
        scaled = (limitMap * torch.tanh(latent.detach()) * 255.0).squeeze(0).cpu()
        deltaInt = torch.floor(scaled + torch.rand(scaled.shape, generator=gen)).clamp(-limit, limit).permute(1, 2, 0).numpy()
        origArr = np.asarray(origRgb, dtype=np.float64)
        outArr = np.clip(origArr + deltaInt, 0, 255).astype(np.uint8)
        outPil = Image.fromarray(outArr)
        hasStego = stegoMode == "combined" and bool(stegoText.strip() or (stegoOpts or {}).get("mark"))
        outBytes = self.encodeOutputImage(outPil, fileExt, hasStego, stegoText, exifBytes, iccProfile, stegoOpts, alpha)
        finalArr = np.asarray(Image.open(io.BytesIO(outBytes)).convert("RGB"), dtype=np.float64)
        mse = float(np.mean((finalArr - origArr) ** 2))
        psnr = 10.0 * math.log10((255.0 ** 2) / max(mse, 1e-10))
        return outBytes, origW, origH, psnr, float(np.abs(finalArr - origArr).max())


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
        if HISTORY_FILE.exists():
            try:
                self.history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                self.history = []

    def saveHistory(self) -> None:
        try:
            atomicWrite(HISTORY_FILE, json.dumps(self.history[:100], indent=2))
        except Exception:
            pass


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


def isTrustedRequest(host: Optional[str], origin: Optional[str], port: int) -> bool:
    """Blocks cross-site and DNS-rebinding POSTs: browsers let any website reach localhost."""
    allowed = (f"127.0.0.1:{port}", f"localhost:{port}")
    return host in allowed and (origin is None or origin in tuple(f"http://{a}" for a in allowed))


def runServer(port: int = 7860, debugMode: bool = False, noBrowser: bool = False) -> None:
    actualPort = port
    print("=" * 96)
    TermLog.emit(
        f"{APP_NAME} {TermLog.CYAN}{APP_VERSION}{TermLog.RESET} // Python {sys.version.split()[0]}",
        "bootstrap.py",
        "INFO",
    )

    algoMgr = AlgoPluginManager(ALGOS_DIR)
    rebuilt = [k for k, item in algoMgr.plugins.items() if not item["notRebuilt"]]
    if not CFG.overrideHardware:
        CFG.favoriteAlgos = [k for k in CFG.favoriteAlgos if k in rebuilt] or rebuilt[:10]
    mon = TelemetryMonitor()
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
                "cleaner.py",
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

            batch.state = "RUNNING"
            batch.exportDir.mkdir(parents=True, exist_ok=True)
            rt.busy = True
            rt.paused = False
            rt.stopRequested = False
            rt.activeBatch = batch.batchId
            rt.total = len(validFiles)
            qMgr.rev += 1

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
                rt.steps = batch.steps

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
                    outBytes, w, h, psnr, shift = engine.processImage(
                        qfile.rawBytes,
                        fileExt=qfile.ext,
                        epsilon255=batch.epsilon,
                        steps=batch.steps,
                        computeLevel=batch.computeLevel,
                        seed=batch.seed,
                        stegoOpts={"mark": batch.stegoMarkActive, "strength": batch.stegoStrength, "scale": batch.stegoScale, "placement": batch.stegoPlacement},
                        stegoMode=batch.stegoMode,
                        stegoText=batch.stegoTextActive,
                        layers=batch.layers,
                        stepCb=stepCb,
                        controlCb=ctrlCb,
                        emulateDebug=rt.emulateExecution,
                        guidancePrompt=batch.guidancePrompt,
                        geoAnchorLow=batch.geoAnchorLow,
                        geoAnchorHigh=batch.geoAnchorHigh,
                        temporalWeight=batch.temporalWeight,
                        maskAugFactor=batch.maskAugFactor,
                    )
                    stem = Path(qfile.name).stem
                    outExt = qfile.ext
                    if qfile.outPath:
                        outPath = Path(qfile.outPath)
                    else:
                        outPath = batch.exportDir / f"{stem}_lumiya{outExt}"
                        counter = 1
                        while outPath.exists():
                            outPath = batch.exportDir / f"{stem}_lumiya_{counter}{outExt}"
                            counter += 1
                    outPath.write_bytes(outBytes)
                    qfile.outPath = str(outPath)
                    qfile.hasStego = batch.stegoMode in ("combined", "only") and bool(batch.stegoTextActive.strip() or batch.stegoMarkActive)
                    qfile.psnr = psnr
                    qfile.shift = shift
                    qfile.status = "DONE"
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
                    qMgr.rev += 1
                    TermLog.emit(f"Error processing {qfile.name}: {exc}", "worker.py", "ERROR")

            if not rt.stopRequested and batch.state != "STOPPED":
                batch.state = "COMPLETED"
            elif rt.stopRequested:
                batch.state = "STOPPED"
            qMgr.rev += 1

            algoMgr.rev += 1
            CFG.save()
            cleanMemoryAndStorage(ROOT_DIR, RESULTS_ROOT, qMgr.batches, engine, clearRawBytes=False)
        finally:
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

            if parsed.path == "/":
                body = UI_FILE.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif parsed.path in ("/lumiya_blk.ico", "/lumiya_t.ico"):
                icoName = parsed.path.lstrip("/")
                icoPath = ROOT_DIR / icoName
                if not icoPath.exists() and (ROOT_DIR / "assets" / icoName).exists():
                    icoPath = ROOT_DIR / "assets" / icoName
                if icoPath.exists():
                    data = icoPath.read_bytes()
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "image/x-icon")
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
                            "hw": mon.read().__dict__,
                            "cfg": {k: v for k, v in CFG.__dict__.items() if k != "stegoMark"},
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
                                "history": rt.history[:40],
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
                text = MANIFEST_FILE.read_text(encoding="utf-8") if MANIFEST_FILE.exists() else "No install_manifest.log found."
                self.sendJson({"manifest": text})
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            if not isTrustedRequest(self.headers.get("Host"), self.headers.get("Origin"), actualPort):
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            length = int(self.headers.get("Content-Length", "0"))
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
                # The name comes from the page, so it must be one plain folder directly inside results.
                if not name or folder.resolve().parent != RESULTS_ROOT.resolve() or not folder.is_dir():
                    self.sendJson({"ok": False})
                    return
                openPathForeground(folder)
                self.sendJson({"ok": True})

            elif parsed.path == "/api/batch_action":
                info = json.loads(rawBody.decode("utf-8")) if rawBody else {}
                act = info.get("action", "")
                bid = info.get("batchId", "")
                b = qMgr.batches.get(bid)

                if act == "run" and not rt.busy and b and (engine.majorDepsReady or rt.emulateExecution or b.stegoMode == "only"):
                    okCfg, errCfg = validateBatchConfig(b)
                    if not okCfg:
                        self.sendJson({"ok": False, "error": errCfg})
                        return
                    threading.Thread(target=executeBatch, args=(bid,), daemon=True).start()
                    self.sendJson({"ok": True})
                elif act == "stop" and rt.busy and rt.activeBatch == bid:
                    rt.stopRequested = True
                    self.sendJson({"ok": True})
                elif act == "restart" and not rt.busy and b:
                    okCfg, errCfg = validateBatchConfig(b)
                    if not okCfg:
                        self.sendJson({"ok": False, "error": errCfg})
                        return
                    if any(f.valid and not f.rawBytes for f in b.files):
                        self.sendJson({"ok": False, "error": "Originals were released from memory. Add the photos again to redo this batch."})
                        return
                    for f in b.files:
                        if f.valid:
                            f.status = "STAGED"
                    b.state = "STAGED"
                    qMgr.rev += 1
                    threading.Thread(target=executeBatch, args=(bid,), daemon=True).start()
                    self.sendJson({"ok": True})
                elif act == "update_params" and b:
                    if "epsilon" in info:
                        b.epsilon = max(1.0, min(32.0, float(info["epsilon"])))
                    if float(info.get("computeLevel", 0)) in (0.25, 0.5, 1.0, 2.0):
                        b.computeLevel = float(info["computeLevel"])
                    if "seed" in info:
                        b.seed = max(0, int(info["seed"]))
                    if "stegoStrength" in info:
                        b.stegoStrength = max(1.0, min(16.0, float(info["stegoStrength"])))
                    if "stegoScale" in info:
                        b.stegoScale = max(5.0, min(100.0, float(info["stegoScale"])))
                    if info.get("stegoPlacement") in PLACEMENTS:
                        b.stegoPlacement = info["stegoPlacement"]
                    if info.get("stegoPayload") in ("text", "image"):
                        b.stegoPayload = info["stegoPayload"]
                    if "stegoMark" in info:
                        b.stegoMark = str(info["stegoMark"])
                    if "guidancePrompt" in info:
                        b.guidancePrompt = str(info["guidancePrompt"])
                    if "geoAnchorLow" in info:
                        b.geoAnchorLow = max(1.0, min(8.0, float(info["geoAnchorLow"])))
                    if "geoAnchorHigh" in info:
                        b.geoAnchorHigh = max(1.1, min(10.0, float(info["geoAnchorHigh"])))
                    if "temporalWeight" in info:
                        b.temporalWeight = max(0.0, min(1.0, float(info["temporalWeight"])))
                    if "maskAugFactor" in info:
                        b.maskAugFactor = max(0.2, min(2.0, float(info["maskAugFactor"])))
                    if "stegoMode" in info and str(info["stegoMode"]) in ("off", "combined", "only"):
                        b.stegoMode = str(info["stegoMode"])
                    if "stegoText" in info:
                        b.stegoText = str(info["stegoText"])
                    if "layers" in info and isinstance(info["layers"], dict):
                        b.layers = dict(info["layers"])
                    qMgr.rev += 1
                    okCfg, errCfg = validateBatchConfig(b)
                    self.sendJson({"ok": okCfg, "error": errCfg})
                elif act == "reorder_file":
                    res = qMgr.reorderOrSplitFile(
                        srcBatchId=bid,
                        fileId=str(info.get("fileId", "")),
                        targetBatchId=str(info.get("targetBatchId", bid)),
                        targetIndex=int(info.get("targetIndex", 0)),
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
                    qMgr.deleteBatch(bid, keepExports=bool(info.get("keepExports")))
                    self.sendJson({"ok": True})
                elif act == "remove_file":
                    fid = info.get("fileId", "")
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
                info = json.loads(rawBody.decode("utf-8")) if rawBody else {}
                cmd = info.get("cmd", "")
                if cmd == "toggle_emulate":
                    rt.emulateExecution = not rt.emulateExecution
                elif cmd == "mock_deps":
                    stateVal = bool(info.get("state", True))
                    for k in ("torch", "cuda", "diffusers", "transformers", "pil", "psutil"):
                        DEPS_STATUS[k] = stateVal
                    # Modules that truly failed to import must stay off or the telemetry thread dies.
                    DEPS_STATUS["psutil"] = stateVal and psutil is not None
                    DEPS_STATUS["pil"] = stateVal and Image is not None
                elif cmd == "sim_thermal":
                    mon.debugOverride["tempState"] = info.get("state", "normal")
                    mon.debugOverride["tempC"] = float(info.get("tempC", 50.0))
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
                info = json.loads(rawBody.decode("utf-8")) if rawBody else {}
                if info.get("action") == "delete":
                    res = algoMgr.deleteCustomAlgo(info.get("algoId", ""))
                    self.sendJson({**res, "algos": algoMgr.listMetadata()})
                else:
                    self.sendJson({"ok": False})

            elif parsed.path == "/api/save_config":
                newCfg = json.loads(rawBody.decode("utf-8"))
                for k, v in newCfg.items():
                    if hasattr(CFG, k):
                        setattr(CFG, k, v)
                CFG.save()
                if "overrideHardware" in newCfg:
                    algoMgr.rev += 1
                self.sendJson({"ok": True})

            elif parsed.path == "/api/rescan_algos":
                algos = algoMgr.scanAlgos()
                self.sendJson({"ok": True, "algos": algos})

            elif parsed.path == "/api/system_maint":
                cmdType = qs.get("cmd", [""])[0]
                if cmdType == "install":
                    subprocess.Popen(["cmd.exe", "/c", "start", "PORTtralica Installer", "cmd.exe", "/k", str(ROOT_DIR / "install.bat")])
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
                        # No server.shutdown(): it ends the main thread, which can exit with code 0 before this line runs.
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
        TermLog.emit(f"APS Socket Fallback: Listening on port {TermLog.CYAN}{actualPort}{TermLog.RESET} (preferred {port} was busy)", "server.py", "INFO")

    url = f"http://127.0.0.1:{actualPort}"
    TermLog.emit(f"WebUI listening on {TermLog.GREEN}\"{url}\"{TermLog.RESET}", "server.py", "OK")
    print("=" * 96)
    if not noBrowser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        cleanMemoryAndStorage(ROOT_DIR, RESULTS_ROOT, qMgr.batches, engine)
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.worker:
        runServer(port=args.port, debugMode=args.debug, noBrowser=args.no_browser)
    else:
        # Resolve preferred starting port via APS so supervisor and worker maintain consistent port across restarts
        targetPort = findAvailablePort(args.port)
        firstLaunch = not args.no_browser
        while True:
            cmd = [sys.executable, str(Path(__file__).resolve()), "--worker", "--port", str(targetPort)]
            if args.debug:
                cmd.append("--debug")
            if not firstLaunch:
                cmd.append("--no-browser")
            rc = subprocess.call(cmd, cwd=str(ROOT_DIR))
            firstLaunch = False
            if rc != 42:
                break
            time.sleep(0.25)