"""Hidden visual mark + binary LSB steganography stored across high-definition layers.

Lossless files carry the visual mark at native resolution (H x W) in bit 0 of every RGB channel using
2x supersampled TrueType typography and Lanczos contour resampling so bit-plane forensic tools display
razor-sharp vector-grade glyphs and logos rather than blocky low-poly cells.
Every marked file also carries a smooth QIM cell layer that survives JPEG recompression and resizing.
Invisible Binary Text mode ('binary') embeds UTF-8 strictly into the top LSB scanlines + container metadata
with zero visible bit-plane glyph stamp.
"""
from __future__ import annotations

import base64
import io
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:
    Image = ImageDraw = ImageFont = ImageOps = None  # type: ignore

from stego.lsb import applySteganographyPil, extractSteganographyPil

GRID_CHOICES = (128, 192, 256, 384, 512)
MIN_CELL_PX = 6
MAX_MARK_SIDE = 2000
CARRIER_SEED = 0x4C4D59
MAX_STRENGTH = 16
MIN_AGREEMENT = 0.68
PLACEMENTS = ("center", "top-left", "top-right", "bottom-left", "bottom-right", "tile")
UNUSABLE = "This image will not work: it needs a transparent background, otherwise it is one solid color with no shape to embed."

_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\calibrib.ttf",
    r"C:\Windows\Fonts\consolab.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/google-noto-vf/NotoSans[wght].ttf",
    "/usr/share/fonts/liberation-sans/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)
_FC_MATCH_CACHE: Optional[str] = None


class MarkError(ValueError):
    """A mark image the user must replace; the message is shown to them."""


def _loadHighResFont(sizePx: int = 360) -> Any:
    """Loads a crisp vector TrueType font at high resolution across Windows, macOS, and all Linux distros."""
    global _FC_MATCH_CACHE
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size=sizePx)
            except Exception:
                continue
    if _FC_MATCH_CACHE is None:
        _FC_MATCH_CACHE = ""
        if shutil.which("fc-match"):
            try:
                out = subprocess.check_output(
                    ["fc-match", "-f", "%{file}", "sans-serif:bold"], stderr=subprocess.DEVNULL, timeout=1.5
                ).decode("utf-8", errors="replace").strip()
                if out and Path(out).exists():
                    _FC_MATCH_CACHE = out
            except Exception:
                pass
    if _FC_MATCH_CACHE:
        try:
            return ImageFont.truetype(_FC_MATCH_CACHE, size=sizePx)
        except Exception:
            pass
    return ImageFont.load_default(size=sizePx)


def toB64Png(mask: np.ndarray) -> str:
    """Encodes a boolean or 8-bit grayscale mask as a compact PNG."""
    buf = io.BytesIO()
    if mask.dtype == bool:
        arr = mask.astype(np.uint8) * 255
    else:
        arr = np.clip(mask, 0, 255).astype(np.uint8)
    Image.fromarray(arr, mode="L").save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def prepareMark(rawBytes: bytes) -> Tuple[str, bool]:
    """Extracts smooth 8-bit alpha mask from a transparent PNG up to 2000px with Lanczos resampling."""
    with Image.open(io.BytesIO(rawBytes)) as im:
        rgba = ImageOps.exif_transpose(im).convert("RGBA")
    compressed = max(rgba.size) > MAX_MARK_SIDE
    rgba.thumbnail((MAX_MARK_SIDE, MAX_MARK_SIDE), Image.Resampling.LANCZOS)
    alphaArr = np.asarray(rgba.getchannel("A"), dtype=np.uint8)
    binaryCheck = alphaArr > 96
    if not 0.0005 < binaryCheck.mean() < 0.995:
        raise MarkError(UNUSABLE)
    return toB64Png(alphaArr), compressed


def textMask(text: str) -> np.ndarray:
    """Renders text at 360px TrueType resolution as a smooth 8-bit anti-aliased grayscale mask."""
    cleanText = (text or "PORTtralica Lumiya").strip() or "PORTtralica Lumiya"
    font = _loadHighResFont(360)
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    left, top, right, bottom = probe.textbbox((0, 0), cleanText, font=font)
    w = max(1, right - left + 24)
    h = max(1, bottom - top + 24)
    im = Image.new("L", (w, h), 0)
    ImageDraw.Draw(im).text((12 - left, 12 - top), cleanText, fill=255, font=font)
    return np.asarray(im, dtype=np.uint8)


def gridShape(width: int, height: int, gridShort: int) -> Tuple[int, int]:
    short = max(1, min(width, height))
    return max(8, round(gridShort * height / short)), max(8, round(gridShort * width / short))


def chooseGrid(width: int, height: int) -> int:
    """Finest grid whose cells stay large enough to survive compression."""
    fitting = [g for g in GRID_CHOICES if min(width, height) / g >= MIN_CELL_PX]
    return fitting[-1] if fitting else GRID_CHOICES[0]


def cellKeys(gridH: int, gridW: int) -> Tuple[np.ndarray, np.ndarray]:
    """Per-cell sign and dither. Generated at a fixed size and cut, so they do not depend on aspect ratio."""
    side = max(gridH, gridW)
    rng = np.random.default_rng(CARRIER_SEED)
    sign = rng.choice((-1.0, 1.0), size=(side, side))
    dither = rng.random((side, side))
    return sign[:gridH, :gridW], dither[:gridH, :gridW]


def quadPattern(sign: np.ndarray) -> np.ndarray:
    """Expands each cell into a signed 2x2 checker on a grid twice as fine."""
    pattern = np.repeat(np.repeat(sign, 2, axis=0), 2, axis=1)
    pattern[0::2, 1::2] *= -1
    pattern[1::2, 0::2] *= -1
    return pattern


def readCells(gray: Any, gridH: int, gridW: int, sign: np.ndarray) -> np.ndarray:
    small = np.asarray(gray.resize((gridW * 2, gridH * 2), Image.Resampling.BOX), dtype=np.float64)
    return (small * quadPattern(sign)).reshape(gridH, 2, gridW, 2).mean(axis=(1, 3))


def cellBits(cells: np.ndarray, dither: np.ndarray, step: float) -> np.ndarray:
    return np.rint(cells / step - 2.0 * dither).astype(np.int64) % 2


def layoutMask(mask: np.ndarray, gridH: int, gridW: int, scalePct: float, placement: str) -> np.ndarray:
    """Places the mark on the target grid using BOX/Lanczos grayscale resampling so curves and thin strokes stay crisp."""
    grayMask = (mask.astype(np.uint8) * 255) if mask.dtype == bool else np.clip(mask, 0, 255).astype(np.uint8)
    ratio = min(gridH / max(1, grayMask.shape[0]), gridW / max(1, grayMask.shape[1])) * min(max(scalePct, 5.0), 100.0) / 100.0
    markH = max(1, min(gridH, round(grayMask.shape[0] * ratio)))
    markW = max(1, min(gridW, round(grayMask.shape[1] * ratio)))
    resampleMode = Image.Resampling.LANCZOS if (markW >= grayMask.shape[1] or markH >= grayMask.shape[0]) else Image.Resampling.BOX
    resized = Image.fromarray(grayMask, mode="L").resize((markW, markH), resampleMode)
    mark = np.asarray(resized, dtype=np.uint8) > 80
    out = np.zeros((gridH, gridW), dtype=bool)
    if placement == "tile":
        stepY = max(1, markH + markH // 4)
        stepX = max(1, markW + markW // 4)
        for y in range(0, gridH, stepY):
            for x in range(0, gridW, stepX):
                h, w = min(markH, gridH - y), min(markW, gridW - x)
                out[y:y + h, x:x + w] |= mark[:h, :w]
        return out
    margin = max(2, gridH // 32)
    y = {"top": margin, "bottom": max(0, gridH - markH - margin)}.get(placement.split("-")[0], (gridH - markH) // 2)
    x = {"left": margin, "right": max(0, gridW - markW - margin)}.get(placement.split("-")[-1], (gridW - markW) // 2)
    out[y:y + markH, x:x + markW] = mark[: min(markH, gridH - y), : min(markW, gridW - x)]
    return out


def computeMaskBBox(mask: np.ndarray) -> Optional[Dict[str, int]]:
    """Computes the bounding box of active mark pixels for Inspect stage overlay."""
    ys, xs = np.where(mask > 0)
    if ys.size == 0 or xs.size == 0:
        return None
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    return {"x": x0, "y": y0, "w": max(1, x1 - x0), "h": max(1, y1 - y0)}


def embedMark(
    rgbImg: Any,
    text: str = "",
    opts: Optional[Dict[str, Any]] = None,
    lossless: bool = False,
    *,
    payload: Optional[str] = None,
    markB64: Optional[str] = None,
    strength: Optional[float] = None,
    scale: Optional[float] = None,
    placement: Optional[str] = None,
    writeBit0: Optional[bool] = None,
) -> Any:
    """Embeds either an Invisible Binary LSB frame ('binary') or a High-Definition Visual + QIM Mark ('text' / 'image')."""
    cfg = dict(opts or {})
    if payload is not None:
        cfg["payload"] = payload
    if markB64 is not None:
        cfg["mark"] = markB64
    if strength is not None:
        cfg["strength"] = strength
    if scale is not None:
        cfg["scale"] = scale
    if placement is not None:
        cfg["placement"] = placement
    useLossless = bool(writeBit0) if writeBit0 is not None else bool(lossless)

    payloadMode = str(cfg.get("payload", "image" if cfg.get("mark") else "text")).lower()
    if payloadMode == "binary":
        return applySteganographyPil(rgbImg, text, cyclic=False)

    encoded = cfg.get("mark") or ""
    if (payloadMode == "image" or not text) and encoded:
        mask = np.asarray(Image.open(io.BytesIO(base64.b64decode(encoded))).convert("L"), dtype=np.uint8)
    else:
        mask = textMask(text)

    width, height = rgbImg.size
    gridH, gridW = gridShape(width, height, chooseGrid(width, height))
    scalePct = float(cfg.get("scale", 40.0))
    placeStr = str(cfg.get("placement", "center"))
    placed = layoutMask(mask, gridH, gridW, scalePct, placeStr)
    step = max(1.0, min(float(MAX_STRENGTH), round(float(cfg.get("strength", 4.0)))))
    sign, dither = cellKeys(gridH, gridW)
    quad = quadPattern(sign)
    base = np.asarray(rgbImg.convert("RGB"), dtype=np.float32)
    offset = np.zeros((gridH, gridW))
    for _ in range(3):
        carrierGrid = (quad * np.repeat(np.repeat(offset, 2, 0), 2, 1)).astype(np.float32)
        full = np.asarray(Image.fromarray(carrierGrid, mode="F").resize((width, height), Image.Resampling.NEAREST))
        marked = Image.fromarray(np.clip(np.rint(base + full[..., None]), 0, 255).astype(np.uint8))
        cells = readCells(marked.convert("L"), gridH, gridW, sign)
        target = (np.rint((cells / step - 2.0 * dither - placed) / 2.0) * 2.0 + placed + 2.0 * dither) * step
        offset = np.clip(offset + target - cells, -step, step)
    if not useLossless:
        return marked
    native = layoutMask(mask, height, width, scalePct, placeStr)
    outArr = (np.asarray(marked) & 0xFE) | native[..., None].astype(np.uint8)
    return Image.fromarray(outArr)


def boxBlur(arr: np.ndarray) -> np.ndarray:
    pad = np.pad(arr, 1, mode="edge")
    total = pad.cumsum(0).cumsum(1)
    total = np.pad(total, ((1, 0), (1, 0)))
    return (total[3:, 3:] - total[:-3, 3:] - total[3:, :-3] + total[:-3, :-3]) / 9.0


def readBitPlane(arr: np.ndarray) -> Optional[np.ndarray]:
    """Returns the native H x W mark if bit 0 is a coherent image shared across RGB channels."""
    bits = arr & 1
    if (bits[..., 0] == bits[..., 1]).mean() < 0.96 or (bits[..., 0] == bits[..., 2]).mean() < 0.96:
        return None
    plane = ((bits[..., 0].astype(np.uint8) + bits[..., 1].astype(np.uint8) + bits[..., 2].astype(np.uint8)) >= 2)
    coverage = float(plane.mean())
    if not (0.0003 < coverage < 0.96):
        return None
    agreement = (float((plane[1:] == plane[:-1]).mean()) + float((plane[:, 1:] == plane[:, :-1]).mean())) / 2.0
    return plane if agreement >= 0.88 else None


def analyzeMark(rawBytes: bytes, pilImg: Optional[Any] = None) -> Dict[str, Any]:
    """Blind read. Finds the QIM cell mark (survives JPEG/resizing), then upgrades to the crisp native bit-0 plane
    when the file is lossless."""
    if pilImg is not None:
        rgb = pilImg.convert("RGB")
    else:
        with Image.open(io.BytesIO(rawBytes)) as im:
            rgb = im.convert("RGB")
    width, height = rgb.size
    rgbArr = np.asarray(rgb)

    binRes = extractSteganographyPil(rawBytes)
    binFound = bool(binRes.get("found"))

    # 1. Multi-grid QIM cell recovery; survives JPEG and resizing, and every Lumiya mark carries it
    gray = rgb.convert("L")
    best, bestBits = 0.5, np.zeros((GRID_CHOICES[0], GRID_CHOICES[0]), dtype=np.int64)
    for gridShort in GRID_CHOICES:
        gridH, gridW = gridShape(*gray.size, gridShort)
        sign, dither = cellKeys(gridH, gridW)
        cells = readCells(gray, gridH, gridW, sign)
        for step in range(1, MAX_STRENGTH + 1):
            bits = cellBits(cells, dither, float(step))
            agreement = (float((bits[1:] == bits[:-1]).mean()) + float((bits[:, 1:] == bits[:, :-1]).mean())) / 2.0
            if agreement > best:
                best, bestBits = agreement, bits

    shape = bestBits > 0 if best >= 0.9 else boxBlur(bestBits.astype(np.float64)) > 0.5
    coverage = float(shape.mean())
    found = best >= MIN_AGREEMENT and 0.0005 < coverage < 0.98

    # 2. Native full-resolution bit-0 plane: crisp recovery for lossless files. A two-tone flat graphic (40/41 grey)
    # has the same kind of plane, so it only counts when the QIM layer or the LMY1 frame proves Lumiya wrote the file.
    native = readBitPlane(rgbArr) if (found or binFound) else None
    if native is not None:
        agreement = (float((native[1:] == native[:-1]).mean()) + float((native[:, 1:] == native[:, :-1]).mean())) / 2.0
        bbox = computeMaskBBox(native)
        return {
            "found": True,
            "markFound": True,
            "markLsb": True,
            "markScore": round(agreement * 100.0, 1),
            "markCoverage": round(float(native.mean()) * 100.0, 2),
            "markPng": toB64Png(native),
            "markBBox": bbox,
            "markResolution": f"{width}x{height} (Native Bit-0)",
            "binaryFound": binFound,
            "binaryBBox": binRes.get("bbox"),
            "scanlines": binRes.get("scanlines", 0),
            "bitPlane": binRes.get("bitPlane", "LSB Bit-Planes 0 & 1 (RGB)"),
            "message": binRes.get("message", ""),
            "method": "Native Bit-0 + QIM Mark" + (f" + {binRes.get('method')}" if binFound else ""),
        }

    res: Dict[str, Any] = {
        "found": bool(found or binFound),
        "markFound": found,
        "markScore": round(best * 100.0, 1),
        "markLsb": False,
        "binaryFound": binFound,
        "binaryBBox": binRes.get("bbox"),
        "scanlines": binRes.get("scanlines", 0),
        "bitPlane": binRes.get("bitPlane", "LSB Bit-Planes 0 & 1 (RGB)"),
        "message": binRes.get("message", ""),
        "method": ("QIM Cell Mark" + (f" + {binRes.get('method')}" if binFound else "")) if found else binRes.get("method", "None"),
    }
    if found:
        scaleX = width / max(1, shape.shape[1])
        scaleY = height / max(1, shape.shape[0])
        rawBox = computeMaskBBox(shape)
        bbox = (
            {
                "x": int(rawBox["x"] * scaleX),
                "y": int(rawBox["y"] * scaleY),
                "w": int(rawBox["w"] * scaleX),
                "h": int(rawBox["h"] * scaleY),
            }
            if rawBox
            else None
        )
        res.update(
            {
                "markCoverage": round(float(shape.mean()) * 100.0, 2),
                "markPng": toB64Png(shape),
                "markBBox": bbox,
                "markResolution": f"{bestBits.shape[1]}x{bestBits.shape[0]} (QIM Grid)",
            }
        )
    return res


def inspectStego(rawBytes: bytes) -> Dict[str, Any]:
    """Runs every decoder: binary LSB/metadata reader and visual bit-plane/QIM mark analyzer."""
    try:
        return analyzeMark(rawBytes)
    except Exception as exc:
        res = extractSteganographyPil(rawBytes)
        res.update({"markFound": False, "markError": str(exc)})
        return res
