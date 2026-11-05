from __future__ import annotations

import gc
import sys
from pathlib import Path
from typing import Any, Dict


def cleanMemoryAndStorage(
    rootDir: Path,
    resultsDir: Path,
    queuesDict: Dict[str, Any] | None = None,
    engine: Any = None,
    clearRawBytes: bool = True,
) -> Dict[str, Any]:
    """Releases completed RAM byte buffers, unloads idle models, collects GC, purges VRAM, and removes temp files."""
    report = {
        "vramFreedMb": 0.0,
        "ramBuffersCleared": 0,
        "tempFilesRemoved": 0,
        "modelUnloaded": False,
    }

    if engine is not None and hasattr(engine, "unloadModel"):
        try:
            report["modelUnloaded"] = bool(engine.unloadModel())
        except Exception:
            pass

    if "psutil" in sys.modules and sys.modules["psutil"] is not None:
        try:
            psMod = sys.modules["psutil"]
            for proc in psMod.process_iter(["pid", "name", "cmdline"]):
                cmdList = proc.info.get("cmdline") or []
                if "--compute-worker" in cmdList and proc.info.get("pid") != psMod.Process().pid:
                    proc.kill()
                    report["modelUnloaded"] = True
        except Exception:
            pass

    activeExportDirs = set()
    if queuesDict:
        for batch in queuesDict.values():
            bState = getattr(batch, "state", "")
            expDir = getattr(batch, "exportDir", None)
            if bState in ("STAGED", "RUNNING", "PAUSED") and expDir is not None:
                try:
                    activeExportDirs.add(Path(expDir).resolve())
                except OSError:
                    pass
            if clearRawBytes and bState not in ("RUNNING", "PAUSED"):
                for item in getattr(batch, "files", []):
                    outPathStr = getattr(item, "outPath", "")
                    hasDiskExport = bool(outPathStr and Path(outPathStr).is_file())
                    if getattr(item, "rawBytes", None) and getattr(item, "status", "") == "DONE" and hasDiskExport:
                        item.rawBytes = b""
                        report["ramBuffersCleared"] += 1

    gc.collect()

    if "torch" in sys.modules:
        try:
            torchMod = sys.modules["torch"]
            if torchMod.cuda.is_available():
                beforeBytes = torchMod.cuda.memory_reserved(0)
                torchMod.cuda.empty_cache()
                torchMod.cuda.ipc_collect()
                afterBytes = torchMod.cuda.memory_reserved(0)
                report["vramFreedMb"] = round(max(0.0, (beforeBytes - afterBytes) / (1024 ** 2)), 2)
        except Exception:
            pass

    gc.collect()

    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.cdll.ucrtbase._heapmin()
            proc = ctypes.windll.kernel32.GetCurrentProcess()
            ctypes.windll.psapi.EmptyWorkingSet(proc)
        except Exception:
            pass

    for tmpFile in rootDir.glob("*.tmp"):
        try:
            tmpFile.unlink()
            report["tempFilesRemoved"] += 1
        except OSError:
            pass

    if resultsDir.exists():
        for subDir in resultsDir.iterdir():
            if subDir.is_dir():
                try:
                    if subDir.resolve() in activeExportDirs:
                        continue
                except OSError:
                    continue
                for tmpFile in subDir.glob("*.tmp"):
                    try:
                        tmpFile.unlink()
                        report["tempFilesRemoved"] += 1
                    except OSError:
                        pass
                if not any(subDir.iterdir()):
                    try:
                        subDir.rmdir()
                        report["tempFilesRemoved"] += 1
                    except OSError:
                        pass

    return report
