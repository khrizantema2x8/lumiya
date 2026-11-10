"""Configuration schema, safe numeric coercion, atomic persistence, and batch history management."""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from stego.mark import PLACEMENTS

# The one place the version is written; Python, the UI stream and the .bat/.sh launchers all read it from here.
APP_VERSION = "v0.6.076.2530 (Pilot)"
CONFIG_SCHEMA_VERSION = APP_VERSION.split()[0]
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

THEME_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
LEGACY_THEME_ALIASES: Dict[str, str] = {
    "1": "carbon",
    "2": "blue_steel",
    "bluesteel": "blue_steel",
    "3": "tropical",
    "4": "freshen",
    "5": "blue_steel_amere",
    "bluesteel_amere": "blue_steel_amere",
    "amere_blue_steel": "blue_steel_amere",
    "6": "tropical_amere",
    "amere_tropical": "tropical_amere",
    "7": "freshen_amere",
    "amere_freshen": "freshen_amere",
}

# Settings with a fixed set of values; anything else from a request is ignored.
CHOICES: Dict[str, tuple] = {
    "computeBackend": ("auto", "cuda", "opengl", "cpu"),
    "precision": ("fp16", "fp32"),
    "protectionMode": ("photo_only", "all"),
    "resolutionPolicy": ("native_tiled", "strict_native"),
    "eotPreset": ("off", "standard", "aggressive"),
    "stegoMode": ("off", "combined", "only"),
    "stegoPayload": ("text", "binary", "image"),
    "stegoPlacement": PLACEMENTS,
    "computeLevel": (0.25, 0.5, 1.0, 2.0),
}

# (min, max) of every numeric setting: the server clamps with it and the UI sets its inputs' min/max from it.
BOUNDS: Dict[str, tuple] = {
    "epsilon": (1.0, 32.0),
    "geoAnchorLow": (1.0, 8.0),
    "geoAnchorHigh": (1.1, 10.0),
    "temporalWeight": (0.0, 1.0),
    "maskAugFactor": (0.2, 2.0),
    "tempWarnC": (50.0, 80.0),
    "tempCritC": (75.0, 100.0),
    "tempErraticDelta": (3.0, 40.0),
    "loadWarnPct": (40.0, 99.0),
    "stegoStrength": (1.0, 16.0),
    "stegoScale": (5.0, 100.0),
    "seed": (0, 2_147_483_647),
    "steps": (10, MAX_STEPS),
    "workingDim": (256, 2048),
    "reserveVramMb": (200, 4000),
    "jpegQuality": (85, 100),
    "pollMs": (250, 5000),
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


def clampSetting(key: str, val: Any, default: Any) -> Any:
    """Coerces `val` to the type of `default` and clamps it to BOUNDS[key]; unreadable input keeps `default`."""
    lo, hi = BOUNDS[key]
    if isinstance(default, int) and not isinstance(default, bool):
        return safeInt(val, default, lo, hi)
    return safeFloat(val, default, lo, hi)


@dataclass
class SuiteConfig:
    configVersion: str = CONFIG_SCHEMA_VERSION
    theme: str = "carbon"
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
        for rawKey, val in raw.items():
            key = LEGACY_CONFIG_KEYS.get(rawKey, rawKey)
            if key == "configVersion" or not hasattr(self, key):
                continue
            if key == "theme":
                themeRaw = str(val).strip()
                vStr = themeRaw.lower().replace("-", "_").replace(" ", "_").replace("è", "e").replace("é", "e")
                # Any .ltheme id is valid; the aliases only translate spellings older configs saved.
                self.theme = LEGACY_THEME_ALIASES.get(vStr) or (themeRaw if THEME_ID_RE.match(themeRaw) else self.theme)
            elif key in CHOICES:
                if val in CHOICES[key]:
                    setattr(self, key, val)
            elif key in BOUNDS:
                setattr(self, key, clampSetting(key, val, getattr(self, key)))
            elif isinstance(getattr(self, key), bool):
                setattr(self, key, bool(val))
            elif key == "favoriteAlgos" and isinstance(val, list):
                self.favoriteAlgos = [str(x) for x in val]
            elif key == "layers" and isinstance(val, dict):
                self.layers.update({str(k): bool(v) for k, v in val.items()})
            elif key == "algoLastUsed" and isinstance(val, dict):
                self.algoLastUsed.update({str(k): str(v) for k, v in val.items()})
            elif isinstance(val, str) and isinstance(getattr(self, key), str):
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

