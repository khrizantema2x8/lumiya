"""Font discovery for the Tailoring font browser: application fonts come only from identity/fonts, system fonts from
the OS font folders. Reads just the name, OS/2, post and fvar tables with the standard library (no fontTools)."""
from __future__ import annotations

import os
import re
import struct
import sys
import threading
import zlib
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional, Tuple

from core.config import FONT_NAME_RE

FONT_MIME = {
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".ttc": "font/collection",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}
APP_FONT_EXTS = (".ttf", ".otf", ".woff", ".woff2")
SYSTEM_FONT_EXTS = (".ttf", ".otf", ".ttc")
CLASSES = ("serif", "slab", "sans", "script", "monospace", "handwritten", "blackletter", "decorative")
MAX_FONT_BYTES = 64 * 1024 * 1024
MAX_SYSTEM_FILES = 5000

_WEIGHT_WORDS = (
    ("hairline", 100), ("thin", 100), ("extralight", 200), ("ultralight", 200), ("light", 300),
    ("semilight", 350), ("book", 400), ("regular", 400), ("normal", 400), ("medium", 500),
    ("semibold", 600), ("demibold", 600), ("demi", 600), ("extrabold", 800), ("ultrabold", 800),
    ("bold", 700), ("heavy", 900), ("black", 900),
)


class _Tables:
    """Random access to sfnt tables of one face, from a plain sfnt or a WOFF 1.0 file."""

    def __init__(self, fh: BinaryIO, entries: Dict[bytes, Tuple[int, int, int]], woff: bool):
        self.fh = fh
        self.entries = entries  # tag -> (offset, storedLength, origLength)
        self.woff = woff

    def get(self, tag: bytes, limit: int = 1 << 20) -> Optional[bytes]:
        ent = self.entries.get(tag)
        if not ent:
            return None
        off, stored, orig = ent
        if stored > limit or orig > limit:
            return None
        self.fh.seek(off)
        raw = self.fh.read(stored)
        if self.woff and stored < orig:
            raw = zlib.decompress(raw)
        return raw


def _sfntDirectory(fh: BinaryIO, base: int) -> Tuple[bytes, Dict[bytes, Tuple[int, int, int]]]:
    fh.seek(base)
    head = fh.read(12)
    if len(head) < 12:
        raise ValueError("short sfnt header")
    version = head[:4]
    numTables = struct.unpack(">H", head[4:6])[0]
    if numTables > 512:
        raise ValueError("bad table count")
    raw = fh.read(16 * numTables)
    entries = {}
    for i in range(numTables):
        tag, _chk, off, length = struct.unpack(">4sIII", raw[i * 16:i * 16 + 16])
        entries[tag] = (off, length, length)
    return version, entries


def _decodeName(platform: int, raw: bytes) -> str:
    if platform in (0, 3):
        return raw.decode("utf-16-be", errors="ignore")
    return raw.decode("latin-1", errors="ignore")


def _names(data: Optional[bytes]) -> Dict[int, str]:
    """Best English string per name ID: Windows US English first, then any Windows, then Mac Roman."""
    out: Dict[int, Tuple[int, str]] = {}
    if not data or len(data) < 6:
        return {}
    _fmt, count, strOff = struct.unpack(">HHH", data[:6])
    for i in range(count):
        rec = data[6 + i * 12:18 + i * 12]
        if len(rec) < 12:
            break
        platform, _enc, lang, nameId, length, off = struct.unpack(">HHHHHH", rec)
        if nameId not in (1, 2, 4, 6, 16, 17):
            continue
        rank = 0 if (platform == 3 and lang == 0x409) else 1 if platform == 3 else 2 if platform == 1 and lang == 0 else 9
        if rank == 9:
            continue
        text = _decodeName(platform, data[strOff + off:strOff + off + length]).strip().replace("\x00", "")
        if text and (nameId not in out or rank < out[nameId][0]):
            out[nameId] = (rank, text)
    return {k: v[1] for k, v in out.items()}


def classify(familyClass: int, panose: bytes, fixedPitch: bool, family: str) -> str:
    """Photoshop-style class from the OS/2 IBM family class and PANOSE, falling back to the family name."""
    low = family.lower()
    cls = familyClass >> 8
    fam = panose[0] if panose else 0
    serifStyle = panose[1] if len(panose) > 1 else 0
    proportion = panose[3] if len(panose) > 3 else 0
    if fixedPitch or (fam == 2 and proportion == 9) or re.search(r"\b(mono|code|console|courier|typewriter)\b|mono$", low):
        return "monospace"
    if re.search(r"fraktur|blackletter|textura|old english|gothic text|schwabacher", low):
        return "blackletter"
    if fam == 3:
        return "handwritten"
    if cls == 10:
        return "script"
    if fam in (4, 5) or cls in (9, 12):
        return "decorative"
    if cls == 5 or (fam == 2 and serifStyle == 6):
        return "slab"
    if cls == 8 or (fam == 2 and serifStyle in (11, 12, 13, 14, 15)):
        return "sans"
    if cls in (1, 2, 3, 4, 7) or (fam == 2 and 2 <= serifStyle <= 10):
        return "serif"
    if "slab" in low:
        return "slab"
    if "script" in low:
        return "script"
    if re.search(r"hand|marker|brush", low):
        return "handwritten"
    if re.search(r"sans|grotesk|grotesque|gothic", low):
        return "sans"
    if re.search(r"serif|roman|times|garamond|book", low):
        return "serif"
    return ""


def _weightFromStyle(style: str) -> int:
    s = style.lower().replace(" ", "").replace("-", "")
    for word, weight in _WEIGHT_WORDS:
        if word in s:
            return weight
    return 400


def _faceFromTables(t: _Tables, flavor: bytes, fallbackName: str) -> Optional[Dict[str, Any]]:
    names = _names(t.get(b"name"))
    family = names.get(16) or names.get(1) or fallbackName
    style = names.get(17) or names.get(2) or "Regular"
    os2 = t.get(b"OS/2") or b""
    weight, italic, familyClass, panose = 400, False, 0, b""
    if len(os2) >= 64:
        weight = struct.unpack(">H", os2[4:6])[0] or 400
        familyClass = struct.unpack(">h", os2[30:32])[0] & 0xFFFF
        panose = os2[32:42]
        italic = bool(struct.unpack(">H", os2[62:64])[0] & 0x1)
    else:
        weight = _weightFromStyle(style)
        italic = "italic" in style.lower() or "oblique" in style.lower()
    post = t.get(b"post") or b""
    fixedPitch = len(post) >= 16 and struct.unpack(">I", post[12:16])[0] != 0
    wght: Optional[Tuple[int, int]] = None
    fvar = t.get(b"fvar")
    if fvar and len(fvar) >= 16:
        axesOff, _res, axisCount, axisSize = struct.unpack(">HHHH", fvar[4:12])
        for i in range(axisCount):
            a = fvar[axesOff + i * axisSize:axesOff + i * axisSize + 20]
            if len(a) >= 20 and a[:4] == b"wght":
                lo, _dflt, hi = (v / 65536 for v in struct.unpack(">iii", a[4:16]))
                wght = (int(lo), int(hi))
    return {
        "family": family.strip()[:64],
        "style": style.strip()[:64],
        "postscript": names.get(6, ""),
        "weight": max(1, min(1000, int(weight))),
        "italic": italic,
        "cls": classify(familyClass, panose, fixedPitch, family),
        "fmt": "otf" if flavor == b"OTTO" else "ttf",
        "variable": wght is not None,
        "wght": list(wght) if wght else None,
    }


def _nameFromFilename(path: Path) -> Tuple[str, str]:
    """'IBMPlexSans-BoldItalic[wght]' -> ('IBM Plex Sans', 'BoldItalic'); used when the tables cannot be read."""
    stem = re.sub(r"\[.*?\]", "", path.stem)
    fam, _, style = stem.partition("-")
    fam = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", fam).replace("_", " ").strip()
    if style.lower() in ("variable", "vf"):
        style = ""
    return fam or path.stem, style or "Regular"


def readFontFaces(path: Path) -> List[Dict[str, Any]]:
    """All faces in one font file; [] when it is not a readable font."""
    try:
        if not path.is_file() or path.stat().st_size > MAX_FONT_BYTES:
            return []
        with path.open("rb") as fh:
            sig = fh.read(4)
            if sig == b"wOF2":
                # WOFF2 tables are Brotli-compressed; without a Brotli module only the header and file name are usable.
                flavor = fh.read(4)
                fam, style = _nameFromFilename(path)
                isItalic = "italic" in style.lower() or "oblique" in style.lower()
                variable = "variable" in path.stem.lower() or "[" in path.stem
                return [{
                    "family": fam[:64], "style": style[:64], "postscript": "", "weight": _weightFromStyle(style),
                    "italic": isItalic, "cls": classify(0, b"", False, fam), "fmt": "otf" if flavor == b"OTTO" else "ttf",
                    "variable": variable, "wght": [100, 900] if variable else None,
                }]
            if sig == b"wOFF":
                head = fh.read(40)
                flavor = head[:4]
                numTables = struct.unpack(">H", head[8:10])[0]
                if numTables > 512:
                    return []
                raw = fh.read(20 * numTables)
                entries = {}
                for i in range(numTables):
                    tag, off, comp, orig, _chk = struct.unpack(">4sIIII", raw[i * 20:i * 20 + 20])
                    entries[tag] = (off, comp, orig)
                face = _faceFromTables(_Tables(fh, entries, True), flavor, _nameFromFilename(path)[0])
                return [face] if face else []
            if sig == b"ttcf":
                fh.seek(8)
                numFonts = struct.unpack(">I", fh.read(4))[0]
                offsets = struct.unpack(f">{min(numFonts, 64)}I", fh.read(4 * min(numFonts, 64)))
                faces = []
                for off in offsets:
                    flavor, entries = _sfntDirectory(fh, off)
                    face = _faceFromTables(_Tables(fh, entries, False), flavor, _nameFromFilename(path)[0])
                    if face:
                        faces.append(face)
                return faces
            if sig in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
                flavor, entries = _sfntDirectory(fh, 0)
                face = _faceFromTables(_Tables(fh, entries, False), flavor, _nameFromFilename(path)[0])
                return [face] if face else []
    except (OSError, ValueError, struct.error, zlib.error):
        return []
    return []


def scanAppFonts(fontsDir: Path) -> List[Dict[str, Any]]:
    """Faces from identity/fonts (top level only), each with the URL the page loads it from."""
    if not fontsDir.is_dir():
        return []
    out: List[Dict[str, Any]] = []
    root = fontsDir.resolve()
    for p in sorted(fontsDir.iterdir()):
        if p.suffix.lower() not in APP_FONT_EXTS or not p.is_file():
            continue
        if p.resolve().parent != root:
            continue
        for face in readFontFaces(p):
            if FONT_NAME_RE.match(face["family"]):
                face["file"] = p.name
                face["mtime"] = int(p.stat().st_mtime)
                out.append(face)
    return out


def systemFontDirs() -> List[Path]:
    home = Path.home()
    if sys.platform == "win32":
        dirs = [Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"]
        if os.environ.get("LOCALAPPDATA"):
            dirs.append(Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "Windows" / "Fonts")
    elif sys.platform == "darwin":
        dirs = [Path("/System/Library/Fonts"), Path("/Library/Fonts"), home / "Library" / "Fonts"]
    else:
        dirs = [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), home / ".local" / "share" / "fonts", home / ".fonts"]
    return [d for d in dirs if d.is_dir()]


_systemCache: Optional[List[Dict[str, Any]]] = None
_systemLock = threading.Lock()


def scanSystemFonts(refresh: bool = False) -> List[Dict[str, Any]]:
    """Faces installed on this computer, without file paths. Cached for the process; refresh=True rescans."""
    global _systemCache
    with _systemLock:
        if _systemCache is not None and not refresh:
            return _systemCache
        out: List[Dict[str, Any]] = []
        seen = set()
        count = 0
        for d in systemFontDirs():
            for dirpath, _dirs, files in os.walk(d):
                for name in files:
                    if not name.lower().endswith(SYSTEM_FONT_EXTS):
                        continue
                    count += 1
                    if count > MAX_SYSTEM_FILES:
                        break
                    for face in readFontFaces(Path(dirpath) / name):
                        key = (face["family"], face["style"])
                        if key in seen or not FONT_NAME_RE.match(face["family"]):
                            continue
                        seen.add(key)
                        out.append(face)
        _systemCache = out
        return out
