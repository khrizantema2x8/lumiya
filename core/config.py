"""Configuration schema, safe numeric coercion, atomic persistence, and batch history management."""
from __future__ import annotations

import json
import os
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

CONFIG_SCHEMA_VERSION = "v0.6.073.8820"
MAX_STEPS = 5000
VALID_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff")

LEGACY_CONFIG_KEYS: Dict[str, str] = {
    "backend": "computeBackend",
    "eps": "epsilon",
    "budget": "epsilon",
    "compute": "computeLevel",
    "dim": "workingDim",
    "ramSpillover": "allowRamSpillover",
    "vramHeadroomMb": "reserveVramMb",
}

DEFAULT_ALGO_IDS = (
    "photoguard",
    "mist",
    "srim",
    "blurguard",
    "diffusionguard",
    "anti_inpainting",
    "antipure",
    "promptflare",
    "decontext",
    "idguardian",
    "idprotector",
    "metacloak",
    "antiprompt",
    "veto",
    "vid_freeze",
    "anti_i2v",
    "diffvax",
    "fastprotect",
    "tc_uap",
    "chronolock",
    "mirage",
    "genptw",
    "tag_wm",
    "obliviate",
)


def atomicWrite(path: Path, text: str) -> None:
    """Writes via a sibling file so a crash mid-save cannot leave a truncated file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmpPath = path.with_name(f"{path.name}.{threading.get_ident()}.partial")
    tmpPath.write_text(text, encoding="utf-8")
    os.replace(tmpPath, path)


def safeFloat(val: Any, default: float, minVal: float | None = None, maxVal: float | None = None) -> float:
    try:
        if val is None or (isinstance(val, str) and not val.strip()):
            out = float(default)
        else:
            out = float(val)
    except (ValueError, TypeError):
        out = float(default)
    if minVal is not None:
        out = max(minVal, out)
    if maxVal is not None:
        out = min(maxVal, out)
    return out


def safeInt(val: Any, default: int, minVal: int | None = None, maxVal: int | None = None) -> int:
    try:
        if val is None or (isinstance(val, str) and not val.strip()):
            out = int(default)
        else:
            out = int(float(val))
    except (ValueError, TypeError):
        out = int(default)
    if minVal is not None:
        out = max(minVal, out)
    if maxVal is not None:
        out = min(maxVal, out)
    return out


@dataclass
class SuiteConfig:
    configVersion: str = CONFIG_SCHEMA_VERSION
    computeBackend: str = "auto"
    epsilon: float = 8.0
    computeLevel: float = 1.0
    seed: int = 0
    steps: int = 200
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
    convertPng: bool = True
    pollMs: int = 1000
    tempWarnC: float = 62.0
    tempCritC: float = 85.0
    tempErraticDelta: float = 12.0
    loadWarnPct: float = 85.0
    overrideHardware: bool = False
    allowRamSpillover: bool = True
    protectionMode: str = "photo_only"
    resolutionPolicy: str = "native_tiled"
    eotPreset: str = "standard"
    autoPaperDefaults: bool = True
    stegoMode: str = "off"
    stegoText: str = "PORTtralica Lumiya - Protected Asset"
    stegoPayload: str = "text"
    stegoStrength: float = 4.0
    stegoScale: float = 40.0
    stegoPlacement: str = "center"
    stegoMark: str = ""
    favoriteAlgos: List[str] = field(default_factory=lambda: ["photoguard", "srim", "blurguard", "mist", "idguardian"])
    algoLastUsed: Dict[str, str] = field(default_factory=dict)
    layers: Dict[str, bool] = field(default_factory=lambda: {k: k == "photoguard" for k in DEFAULT_ALGO_IDS})

    def applyDict(self, raw: Dict[str, Any]) -> None:
        floatBounds = {
            "epsilon": (1.0, 32.0),
            "computeLevel": (0.25, 2.0),
            "geoAnchorLow": (1.0, 8.0),
            "geoAnchorHigh": (1.1, 10.0),
            "temporalWeight": (0.0, 1.0),
            "maskAugFactor": (0.2, 2.0),
            "tempWarnC": (35.0, 95.0),
            "tempCritC": (50.0, 105.0),
            "tempErraticDelta": (3.0, 40.0),
            "loadWarnPct": (40.0, 99.0),
            "stegoStrength": (1.0, 16.0),
            "stegoScale": (5.0, 100.0),
        }
        intBounds = {
            "seed": (0, 2_147_483_647),
            "steps": (10, MAX_STEPS),
            "workingDim": (256, 2048),
            "reserveVramMb": (0, 8192),
            "jpegQuality": (60, 100),
            "pollMs": (250, 5000),
        }
        for rawKey, val in raw.items():
            key = LEGACY_CONFIG_KEYS.get(rawKey, rawKey)
            if key == "configVersion" or not hasattr(self, key):
                continue
            if key in floatBounds:
                lo, hi = floatBounds[key]
                setattr(self, key, safeFloat(val, getattr(self, key), lo, hi))
            elif key in intBounds:
                lo, hi = intBounds[key]
                setattr(self, key, safeInt(val, getattr(self, key), lo, hi))
            elif isinstance(getattr(self, key), bool):
                setattr(self, key, bool(val))
            elif key == "favoriteAlgos" and isinstance(val, list):
                self.favoriteAlgos = [str(x) for x in val]
            elif key == "layers" and isinstance(val, dict):
                self.layers.update({str(k): bool(v) for k, v in val.items()})
            elif key == "algoLastUsed" and isinstance(val, dict):
                self.algoLastUsed.update({str(k): str(v) for k, v in val.items()})
            else:
                setattr(self, key, val)
        self.configVersion = CONFIG_SCHEMA_VERSION

    @classmethod
    def defaultInternalDict(cls) -> Dict[str, Any]:
        """Returns a fresh dictionary of all internal default configuration values."""
        return cls().snapshotForStream()

    def snapshotForStream(self) -> Dict[str, Any]:
        """Returns a shallow-copied snapshot of CFG with mutable collections cloned so SSE serialization never races."""
        out: Dict[str, Any] = {}
        for k, v in self.__dict__.items():
            if k == "stegoMark":
                continue
            if isinstance(v, list):
                out[k] = list(v)
            elif isinstance(v, dict):
                out[k] = dict(v)
            else:
                out[k] = v
        return out

    def save(self, configFile: Path) -> None:
        self.configVersion = CONFIG_SCHEMA_VERSION
        atomicWrite(configFile, json.dumps(self.__dict__, indent=2))

    @classmethod
    def load(cls, configFile: Path) -> "SuiteConfig":
        """Loads `configFile`, creating internal defaults for first-time users or migrating/repopulating missing keys on update."""
        cfg = cls()
        target = configFile
        migratedFromRoot = False
        if not target.exists() and (target.parent.parent / target.name).exists():
            target = target.parent.parent / target.name
            migratedFromRoot = True

        if not target.exists():
            # First-time user: materialize internal default config to disk
            try:
                cfg.save(configFile)
            except Exception:
                pass
            return cfg

        needsMigrationSave = migratedFromRoot
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cfg.applyDict(raw)
                # Check if any new schema keys, new algorithm layer keys, legacy keys, or version stamp need repopulating
                if raw.get("configVersion") != CONFIG_SCHEMA_VERSION:
                    needsMigrationSave = True
                elif any(k in raw for k in LEGACY_CONFIG_KEYS):
                    needsMigrationSave = True
                elif any(k not in raw for k in cfg.__dict__):
                    needsMigrationSave = True
                elif isinstance(raw.get("layers"), dict) and any(a not in raw["layers"] for a in DEFAULT_ALGO_IDS):
                    needsMigrationSave = True
            else:
                needsMigrationSave = True
        except Exception:
            # Back up corrupted config file before repopulating defaults so user file is never lost
            try:
                bakPath = configFile.with_suffix(".json.bak")
                shutil.copy2(target, bakPath)
            except Exception:
                pass
            needsMigrationSave = True

        if needsMigrationSave:
            try:
                cfg.save(configFile)
            except Exception:
                pass
        return cfg

