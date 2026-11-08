"""Hardware sensor telemetry via in-process NVML / psutil without per-second subprocess overhead."""
from __future__ import annotations

import ctypes
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


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
    ramUsed: float = 0.0
    ramTotal: float = 0.0
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
    powerLabel: str = "SYS POWER (EST)"
    hardwareTier: str = "T0"


def resolveHardwareTier(hasCuda: bool, vramGb: float) -> str:
    if not hasCuda or vramGb < 4.0:
        return "T0"
    if vramGb < 8.0:
        return "T1"
    if vramGb < 12.0:
        return "T2"
    return "T3"


class TelemetryMonitor:
    def __init__(self, depsStatus: Dict[str, Any], cfgRef: Any, psutilMod: Any, nvidiaSmiBin: str) -> None:
        self.depsStatus = depsStatus
        self.cfg = cfgRef
        self.psutil = psutilMod
        self.nvidiaSmiBin = nvidiaSmiBin
        self.lock = threading.Lock()
        self.snap = SensorSnapshot()
        if self.depsStatus.get("psutil") and self.psutil:
            try:
                vmInit = self.psutil.virtual_memory()
                self.snap.ram = vmInit.percent
                self.snap.ramUsed = round((vmInit.total - vmInit.available) / (1024.0 ** 3), 1)
                self.snap.ramTotal = round(vmInit.total / (1024.0 ** 3), 1)
            except Exception:
                pass
        self.tempWindow: List[float] = []
        self.rawTemps: List[float] = []
        self.debugOverride: Dict[str, Any] = {}
        self.hasCuda = bool(depsStatus.get("cuda"))
        rawGpu = str(depsStatus.get("gpuName", "CPU")) if self.hasCuda else "CPU"
        self.gpuName = (
            rawGpu.replace("NVIDIA ", "")
            .replace("GeForce ", "")
            .replace("Laptop GPU", "Mobile")
            .strip()
        )
        self._nvmlLib: Any = None
        self._nvmlHandle: Any = None
        self._smiFallbackDisabled: bool = False
        self._lastSmiTime: float = 0.0
        self._cachedHw: Tuple[float, float, float, float, str, float, str] = (
            0.0,
            0.0,
            0.0,
            float(depsStatus.get("vramGb", 0.0)),
            "GPU TEMP" if self.hasCuda else "CPU TEMP",
            0.0,
            "GPU POWER" if self.hasCuda else "SYS POWER (EST)",
        )
        self._initNvml()
        threading.Thread(target=self.pollLoop, daemon=True).start()

    def _initNvml(self) -> None:
        """Loads NVML in-process via ctypes to eliminate per-second nvidia-smi.exe subprocess overhead."""
        candidates = (
            ["nvml.dll", r"C:\Windows\System32\nvml.dll", r"C:\Program Files\NVIDIA Corporation\NVSMI\nvml.dll"]
            if sys.platform == "win32"
            else [
                "libnvidia-ml.so.1",
                "libnvidia-ml.so",
                "/usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1",
                "/usr/lib/x86_64-linux-gnu/libnvidia-ml.so",
                "/usr/lib64/libnvidia-ml.so.1",
                "/usr/lib64/libnvidia-ml.so",
                "/usr/lib64/nvidia/libnvidia-ml.so.1",
                "/usr/lib/libnvidia-ml.so.1",
                "/opt/cuda/lib64/libnvidia-ml.so.1",
                "/usr/local/cuda/lib64/libnvidia-ml.so.1",
                "/usr/local/cuda/targets/x86_64-linux/lib/libnvidia-ml.so.1",
                "/run/opengl-driver/lib/libnvidia-ml.so.1",
                "/usr/lib/wsl/lib/libnvidia-ml.so.1",
            ]
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

    def queryHardwareMetrics(self) -> Tuple[float, float, float, float, str, float, str]:
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
                memU, memT = 0.0, float(self.depsStatus.get("vramGb", 0.0))
                if self._nvmlLib.nvmlDeviceGetMemoryInfo(self._nvmlHandle, ctypes.byref(memInfo)) == 0:
                    memU = float(memInfo.used) / (1024.0 ** 3)
                    memT = float(memInfo.total) / (1024.0 ** 3)

                pwrMilli = ctypes.c_uint(0)
                gpuPower = 0.0
                if self._nvmlLib.nvmlDeviceGetPowerUsage(self._nvmlHandle, ctypes.byref(pwrMilli)) == 0:
                    gpuPower = float(pwrMilli.value) / 1000.0

                pwrLbl = "GPU POWER" if gpuPower > 0.5 else "SYS POWER (EST)"
                self._cachedHw = (gpuUtil, tempC, memU, memT, "GPU TEMP", gpuPower, pwrLbl)
                return self._cachedHw
            except Exception:
                pass

        # Avoid spawning nvidia-smi subprocess if CUDA is absent or if it previously failed
        if self.hasCuda and not self._smiFallbackDisabled:
            now = time.time()
            if now - self._lastSmiTime < 5.0:
                return self._cachedHw
            self._lastSmiTime = now
            try:
                cmd = [
                    self.nvidiaSmiBin,
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
                pwrLbl = "GPU POWER" if gpuPower > 0.5 else "SYS POWER (EST)"
                self._cachedHw = (gpuUtil, tempC, memU, memT, "GPU TEMP", gpuPower, pwrLbl)
                return self._cachedHw
            except Exception:
                self._smiFallbackDisabled = True

        cpuTemp = 0.0
        if self.depsStatus.get("psutil") and self.psutil is not None and hasattr(self.psutil, "sensors_temperatures"):
            try:
                temps = self.psutil.sensors_temperatures()
                for entries in temps.values():
                    if entries:
                        cpuTemp = float(entries[0].current)
                        break
            except Exception:
                pass
        if self.depsStatus.get("cuda"):
            vramU = 0.0
            if "torch" in sys.modules:
                try:
                    vramU = float(sys.modules["torch"].cuda.memory_reserved(0)) / (1024.0 ** 3)
                except Exception:
                    pass
            self._cachedHw = (
                0.0,
                cpuTemp,
                vramU,
                float(self.depsStatus.get("vramGb", 0.0)),
                "GPU TEMP",
                0.0,
                "SYS POWER (EST)",
            )
            return self._cachedHw
        self._cachedHw = (0.0, cpuTemp, 0.0, 0.0, "CPU TEMP", 0.0, "SYS POWER (EST)")
        return self._cachedHw

    def smoothTemp(self, tempC: float) -> float:
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

        cfg = getattr(self, "cfg", None)
        erraticDelta = getattr(cfg, "tempErraticDelta", 10.0)
        critC = getattr(cfg, "tempCritC", 88.0)
        warnC = getattr(cfg, "tempWarnC", 75.0)
        if len(self.tempWindow) >= 4:
            deltas = [
                abs(self.tempWindow[i] - self.tempWindow[i - 1])
                for i in range(1, len(self.tempWindow))
            ]
            if sum(1 for d in deltas if d >= erraticDelta) >= 2:
                return "erratic"

            recent = self.tempWindow[-4:]
            if all(t > critC for t in recent):
                return "crit"
            if all(t > warnC for t in recent):
                return "warn"
        return "normal"

    def pollLoop(self) -> None:
        if self.depsStatus.get("psutil") and self.psutil is not None:
            self.psutil.cpu_percent(interval=None)
        while True:
            vm = self.psutil.virtual_memory() if (self.depsStatus.get("psutil") and self.psutil) else None
            cpu = self.psutil.cpu_percent(interval=None) if (self.depsStatus.get("psutil") and self.psutil) else 0.0
            ram = vm.percent if vm else 0.0
            ramU = round((vm.total - vm.available) / (1024.0 ** 3), 1) if vm else 0.0
            ramT = round(vm.total / (1024.0 ** 3), 1) if vm else 0.0
            gpu, tempC, vramU, vramT, sensorLbl, gpuPowerW, pwrLbl = self.queryHardwareMetrics()
            tempC = self.smoothTemp(tempC)

            if "tempC" in self.debugOverride:
                tempC = float(self.debugOverride["tempC"])
            if "gpu" in self.debugOverride:
                gpu = float(self.debugOverride["gpu"])

            tempF = (tempC * 9.0 / 5.0) + 32.0 if tempC > 0 else 0.0
            freeMb = max(0.0, (vramT - vramU) * 1024.0)
            tState = self.evaluateThermalState(tempC)
            powerOut = round(gpuPowerW, 1) if gpuPowerW > 0.5 else round(14.0 + (cpu * 0.42) + (gpu * 0.45), 1)
            hwTier = resolveHardwareTier(bool(self.depsStatus.get("cuda")), float(vramT or self.depsStatus.get("vramGb", 0.0)))

            with self.lock:
                self.snap = SensorSnapshot(
                    cpu=cpu,
                    ram=ram,
                    ramUsed=ramU,
                    ramTotal=ramT,
                    gpuName=self.gpuName,
                    gpu=gpu,
                    vramUsed=vramU,
                    vramTotal=vramT,
                    vramFreeMb=freeMb,
                    tempC=tempC,
                    tempF=tempF,
                    tempSensorLabel=sensorLbl,
                    tempState=tState,
                    powerW=powerOut,
                    powerLabel=pwrLbl,
                    hardwareTier=hwTier,
                )
            time.sleep(max(0.25, self.cfg.pollMs / 1000.0))
