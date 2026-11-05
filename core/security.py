"""Security, filename sanitization, brand asset integrity verification, and localhost origin checks."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }
)

_ILLEGAL_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SEALED_BRAND_HASHES: Dict[str, str] = {}


def sanitizeFilename(filename: str, fallback: str = "image.png") -> str:
    """Strips path traversal, illegal NTFS characters, and prefixes Windows reserved device names."""
    rawName = Path(filename or fallback).name.strip().rstrip(". ")
    if not rawName:
        rawName = fallback
    ext = Path(rawName).suffix
    stem = Path(rawName).stem
    cleanStem = _ILLEGAL_CHARS_RE.sub("_", stem).strip().rstrip(". ") or "image"
    cleanExt = _ILLEGAL_CHARS_RE.sub("", ext).lower()
    if cleanStem.upper() in WINDOWS_RESERVED_NAMES:
        cleanStem = f"_{cleanStem}"
    return f"{cleanStem}{cleanExt}"


def isTrustedRequest(host: Optional[str], origin: Optional[str], port: int) -> bool:
    """Blocks cross-site and DNS-rebinding requests: browsers let any website reach localhost."""
    allowed = (f"127.0.0.1:{port}", f"localhost:{port}")
    return host in allowed and (origin is None or origin in tuple(f"http://{a}" for a in allowed))


def parseJsonBody(rawBody: bytes) -> Dict[str, Any]:
    """Safely decodes a JSON request body without raising unhandled exceptions on malformed payloads."""
    if not rawBody:
        return {}
    try:
        parsed = json.loads(rawBody.decode("utf-8", errors="replace"))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def verifyBrandAssets(rootDir: Path) -> Dict[str, Any]:
    """Computes and verifies SHA-256 digests of official brand assets (logo.png, lumiya_blk.ico, lumiya_t.ico)."""
    assets = ("logo.png", "lumiya_blk.ico", "lumiya_t.ico")
    report: Dict[str, Any] = {"ok": True, "assets": {}, "tampered": []}
    for name in assets:
        p = rootDir / name
        if not p.exists() and (rootDir / "assets" / name).exists():
            p = rootDir / "assets" / name
        if not p.exists():
            report["assets"][name] = {"exists": False, "sha256": ""}
            continue
        try:
            digest = hashlib.sha256(p.read_bytes()).hexdigest().upper()
            if name not in _SEALED_BRAND_HASHES:
                _SEALED_BRAND_HASHES[name] = digest
            matched = _SEALED_BRAND_HASHES[name] == digest
            if not matched:
                report["ok"] = False
                report["tampered"].append(name)
            report["assets"][name] = {"exists": True, "sha256": digest, "verified": matched}
        except Exception as exc:
            report["ok"] = False
            report["assets"][name] = {"exists": True, "error": str(exc), "verified": False}
    return report


def openPathForeground(targetPath: Path) -> None:
    """Opens a folder in the OS file manager safely without shell-interpolating untrusted strings."""
    targetPath.mkdir(parents=True, exist_ok=True)
    resolved = str(targetPath.resolve())
    if sys.platform == "win32":
        try:
            subprocess.Popen(["explorer.exe", resolved], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

