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

    if queuesDict and clearRawBytes:
        for batch in queuesDict.values():
            for item in getattr(batch, "files", []):
                if getattr(item, "rawBytes", None) and getattr(item, "status", "") == "DONE":
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

    for tmpFile in rootDir.glob("*.tmp"):
        try:
            tmpFile.unlink()
            report["tempFilesRemoved"] += 1
        except OSError:
            pass

    if resultsDir.exists():
        for subDir in resultsDir.iterdir():
            if subDir.is_dir():
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
