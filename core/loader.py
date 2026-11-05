"""AST-based algorithm plugin discovery with mtime caching and lazy module execution."""
from __future__ import annotations

import ast
import importlib.util
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.config import DEFAULT_ALGO_IDS

LEGACY_SKIP_DIRS = frozenset({"impress", "fastprotect_tcuap", "genptw_tagwm", "decontext_cad", "mistv2"})


def hardwareBlockReason(meta: Dict[str, Any], depsStatus: Dict[str, Any], allowRamSpillover: bool = False) -> str:
    """Compares the ALGO_META hardware block with the startup hardware scan."""
    hardware = meta.get("hardware", {})
    if hardware.get("requiresCuda") and not depsStatus.get("cuda"):
        return "Requires an NVIDIA CUDA GPU; none was found."
    minVram = float(hardware.get("minVramGb", 0))
    if depsStatus.get("cuda") and minVram > float(depsStatus.get("vramGb", 0)):
        if allowRamSpillover:
            return ""
        return f"Requires {minVram:g} GB VRAM; this system has {depsStatus.get('vramGb', 0):g} GB."
    return ""


class AlgoPluginManager:
    """Discovers pre-packaged algorithms in algos/ with mtime caching and lazy execution."""

    def __init__(self, algosRoot: Path, cfgRef: Any, depsStatus: Dict[str, Any], logFn: Callable[[str, str, str], None]) -> None:
        self.root = algosRoot
        self.root.mkdir(parents=True, exist_ok=True)
        self.cfg = cfgRef
        self.depsStatus = depsStatus
        self.logFn = logFn
        self.plugins: Dict[str, Dict[str, Any]] = {}
        self._mtimeCache: Dict[str, Tuple[float, float, Dict[str, Any]]] = {}
        self.rev: int = 0
        self.scanAlgos()

    @staticmethod
    def extractAstMeta(pyCode: str, fallbackId: str) -> Dict[str, Any]:
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
            self.logFn(f"Lazy import failed for {algoId}: {exc}", "loader.py", "ERROR")
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
            self.logFn(f"Deleted custom algorithm folder {folder.name}", "loader.py", "INFO")
        self.scanAlgos()
        return {"ok": True}

    def scanAlgos(self) -> List[Dict[str, Any]]:
        self.plugins.clear()
        for subDir in sorted(self.root.iterdir()):
            if (
                not subDir.is_dir()
                or subDir.name.startswith("_")
                or subDir.name.startswith(".")
                or subDir.name in LEGACY_SKIP_DIRS
            ):
                continue
            pyPath = subDir / "algo.py"
            if not pyPath.exists():
                pyFiles = sorted(subDir.glob("*.py"))
                if not pyFiles:
                    continue
                pyPath = pyFiles[0]
            mdFile = subDir / "readmyalgo.md"
            try:
                pyMtime = pyPath.stat().st_mtime
                mdMtime = mdFile.stat().st_mtime if mdFile.exists() else 0.0
                cacheKey = str(subDir.resolve())
                cached = self._mtimeCache.get(cacheKey)
                if cached and cached[0] == pyMtime and cached[1] == mdMtime:
                    entry = dict(cached[2])
                    algoId = entry["id"]
                    entry["lastUsed"] = self.cfg.algoLastUsed.get(algoId, "Never")
                    entry["hardwareReason"] = hardwareBlockReason(entry, self.depsStatus, bool(getattr(self.cfg, "allowRamSpillover", True)))
                    self.plugins[algoId] = entry
                    if algoId not in self.cfg.layers:
                        self.cfg.layers[algoId] = False
                    continue

                pyCode = pyPath.read_text(encoding="utf-8", errors="replace")
                meta = self.extractAstMeta(pyCode, subDir.name)

                algoId = meta.get("id", subDir.name)
                shortInfo = meta.get("shortInfo", "Modular defense layer.")
                hasMd = mdFile.exists() and mdFile.stat().st_size > 0
                mdText = mdFile.read_text(encoding="utf-8", errors="replace") if hasMd else ""
                photoCompatible = bool(meta.get("photoCompatible", True))
                weightReady = bool(meta.get("weightReady", bool(meta.get("paper"))))
                blockerReason = str(meta.get("blockerReason", ""))

                entry = {
                    "id": algoId,
                    "name": meta.get("name", subDir.name),
                    "attribution": meta.get("attribution", "Custom Algorithm Plugin"),
                    "shortInfo": shortInfo,
                    "paperUrl": meta.get("paperUrl", "https://arxiv.org/"),
                    "repoUrl": meta.get("repoUrl", ""),
                    "algoClass": meta.get("algoClass", "A"),
                    "tier": meta.get("tier", "T1"),
                    "photoCompatible": photoCompatible,
                    "weightReady": weightReady,
                    "blockerReason": blockerReason,
                    "lastUsed": self.cfg.algoLastUsed.get(algoId, "Never"),
                    "paper": meta.get("paper"),
                    "hardware": meta.get("hardware", {}),
                    "params": meta.get("params", []),
                    "notRebuilt": (not meta.get("paper")) or (not photoCompatible) or (not weightReady),
                    "hardwareReason": hardwareBlockReason(meta, self.depsStatus, bool(getattr(self.cfg, "allowRamSpillover", True))),
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
                self._mtimeCache[cacheKey] = (pyMtime, mdMtime, dict(entry))
                self.plugins[algoId] = entry
                if algoId not in self.cfg.layers:
                    self.cfg.layers[algoId] = False
            except Exception as exc:
                self.logFn(f"Failed scanning algo plugin {subDir.name}: {exc}", "loader.py", "ERROR")
        self.rev += 1
        return self.listMetadata()

    def blockReason(self, plugin: Dict[str, Any]) -> str:
        if not plugin.get("photoCompatible", True):
            return plugin.get("blockerReason") or "This algorithm operates in-generation or on generator weights, not on uploaded photos."
        if self.cfg.overrideHardware:
            return plugin.get("blockerReason", "") if plugin.get("notRebuilt") else ""
        return self.limitReason(plugin)

    @staticmethod
    def limitReason(plugin: Dict[str, Any]) -> str:
        reasons = []
        if plugin.get("hardwareReason"):
            reasons.append(str(plugin["hardwareReason"]))
        if plugin.get("blockerReason"):
            reasons.append(str(plugin["blockerReason"]))
        elif plugin.get("notRebuilt"):
            reasons.append("Not rebuilt yet.")
        return " ".join(reasons)

    def listMetadata(self) -> List[Dict[str, Any]]:
        allowSpill = bool(getattr(self.cfg, "allowRamSpillover", True))
        for k, item in self.plugins.items():
            item["lastUsed"] = self.cfg.algoLastUsed.get(k, "Never")
            item["hardwareReason"] = hardwareBlockReason(item, self.depsStatus, allowSpill)
            item["limitReason"] = self.limitReason(item)
            item["cannotRunReason"] = self.blockReason(item)
            item["cannotRun"] = bool(item["cannotRunReason"])
        return [{k: v for k, v in item.items() if k != "module"} for item in self.plugins.values()]

