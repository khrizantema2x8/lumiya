"""Security, filename sanitization, and localhost origin checks."""
from __future__ import annotations

import hmac
import json
import re
import subprocess
import sys
import urllib.parse
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


def isLoopbackClient(clientIp: str) -> bool:
    """Returns True if the HTTP client IP is strictly local loopback."""
    return clientIp in ("127.0.0.1", "::1", "::ffff:127.0.0.1", "localhost")


def isTrustedRequest(
    host: Optional[str],
    origin: Optional[str],
    port: int,
    allowRemote: bool = False,
    authToken: str = "",
    reqToken: str = "",
) -> bool:
    """Blocks cross-site and DNS-rebinding requests; verifies Origin matches Host even in --listen mode."""
    if authToken and not hmac.compare_digest(reqToken, authToken):
        return False
    if allowRemote:
        if not host:
            return False
        return origin is None or urllib.parse.urlparse(origin).netloc == host
    allowed = (f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}")
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


def openPathForeground(targetPath: Path) -> None:
    """Opens a folder in the OS file manager safely without shell-interpolating untrusted strings."""
    targetPath.mkdir(parents=True, exist_ok=True)
    opener = "explorer.exe" if sys.platform == "win32" else ("open" if sys.platform == "darwin" else "xdg-open")
    try:
        subprocess.Popen([opener, str(targetPath.resolve())], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

