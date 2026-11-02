"""Hidden visual mark stored in two layers.

Lossless files also carry the mark at native resolution in bit 0 of every channel, the standard LSB
image embed that bit-plane tools such as StegSolve display directly.
Every file carries a cell layer: quantization index modulation gives each grid cell one bit, which survives
JPEG and resizing but is coarser and only this reader can show it. Reading needs no original.
"""
from __future__ import annotations

import base64
import io
from typing import Any, Dict, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from stego.lsb import extractSteganographyPil

GRID_CHOICES = (256, 384, 512, 768, 1024)
MIN_CELL_PX = 8
MAX_MARK_SIDE = 2000
CARRIER_SEED = 0x4C4D59
MAX_STRENGTH = 16
MIN_AGREEMENT = 0.68
PLACEMENTS = ("center", "top-left", "top-right", "bottom-left", "bottom-right", "tile")
UNUSABLE = "This image will not work: it needs a transparent background, otherwise it is one solid color with no shape to embed."


class MarkError(ValueError):
    """A mark image the user must replace; the message is shown to them."""


def toB64Png(mask: np.ndarray) -> str:
    buf = io.BytesIO()
    Image.fromarray(mask.astype(np.uint8) * 255).convert("1").save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def prepareMark(rawBytes: bytes) -> tuple:
    """Solid-color transformer: every opaque pixel, whatever its color, becomes the mark; transparency stays empty.

    Returns the mask and whether the image had to be compressed to fit the size limit.
    """
    with Image.open(io.BytesIO(rawBytes)) as im:
        rgba = ImageOps.exif_transpose(im).convert("RGBA")
    compressed = max(rgba.size) > MAX_MARK_SIDE
    rgba.thumbnail((MAX_MARK_SIDE, MAX_MARK_SIDE), Image.Resampling.LANCZOS)
    mask = np.asarray(rgba.getchannel("A")) > 127
    if not 0.0005 < mask.mean() < 0.995:
        raise MarkError(UNUSABLE)
    return toB64Png(mask), compressed


def textMask(text: str) -> np.ndarray:
    font = ImageFont.load_default(size=160)
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    left, top, right, bottom = probe.textbbox((0, 0), text, font=font)
    im = Image.new("L", (max(1, right - left), max(1, bottom - top)), 0)
    ImageDraw.Draw(im).text((-left, -top), text, fill=255, font=font)
    return np.asarray(im) > 127


def gridShape(width: int, height: int, gridShort: int) -> tuple:
    short = min(width, height)
    return round(gridShort * height / short), round(gridShort * width / short)


def chooseGrid(width: int, height: int) -> int:
    """Finest grid whose cells stay large enough to survive compression."""
    fitting = [g for g in GRID_CHOICES if min(width, height) / g >= MIN_CELL_PX]
    return fitting[-1] if fitting else GRID_CHOICES[0]


def cellKeys(gridH: int, gridW: int) -> tuple:
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
    """Places the mark on the grid: 100 percent is the largest undistorted fit, so any orientation works."""
    ratio = min(gridH / mask.shape[0], gridW / mask.shape[1]) * min(scalePct, 100.0) / 100.0
    markH, markW = max(1, min(gridH, round(mask.shape[0] * ratio))), max(1, min(gridW, round(mask.shape[1] * ratio)))
    # A low threshold keeps thin strokes that would otherwise vanish when the shape shrinks.
    mark = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).resize((markW, markH), Image.Resampling.BOX)) > 80
    out = np.zeros((gridH, gridW), dtype=bool)
    if placement == "tile":
        for y in range(0, gridH, markH + markH // 4):
            for x in range(0, gridW, markW + markW // 4):
                h, w = min(markH, gridH - y), min(markW, gridW - x)
                out[y:y + h, x:x + w] |= mark[:h, :w]
        return out
    margin = gridH // 32
    y = {"top": margin, "bottom": gridH - markH - margin}.get(placement.split("-")[0], (gridH - markH) // 2)
    x = {"left": margin, "right": gridW - markW - margin}.get(placement.split("-")[-1], (gridW - markW) // 2)
    out[y:y + markH, x:x + markW] = mark
    return out


def embedMark(rgbImg: Any, text: str, opts: Dict[str, Any], lossless: bool = False) -> Any:
    """Adds the mark to an RGB image; strength limits the cell layer's change per pixel on the 0-255 scale."""
    encoded = opts.get("mark") or ""
    mask = (np.asarray(Image.open(io.BytesIO(base64.b64decode(encoded))).convert("L")) > 127) if encoded else textMask(text)
    width, height = rgbImg.size
    gridH, gridW = gridShape(width, height, chooseGrid(width, height))
    placed = layoutMask(mask, gridH, gridW, float(opts.get("scale", 40.0)), str(opts.get("placement", "center")))
    step = max(1.0, min(float(MAX_STRENGTH), round(float(opts.get("strength", 4.0)))))
    sign, dither = cellKeys(gridH, gridW)
    quad = quadPattern(sign)
    base = np.asarray(rgbImg.convert("RGB"), dtype=np.float32)
    offset = np.zeros((gridH, gridW))
    # Repeated because clipped highlights and the resize do not land exactly on the target on the first pass.
    for _ in range(3):
        full = np.asarray(Image.fromarray((quad * np.repeat(np.repeat(offset, 2, 0), 2, 1)).astype(np.float32), mode="F").resize((width, height), Image.Resampling.NEAREST))
        marked = Image.fromarray(np.clip(np.rint(base + full[..., None]), 0, 255).astype(np.uint8))
        cells = readCells(marked.convert("L"), gridH, gridW, sign)
        target = (np.rint((cells / step - 2.0 * dither - placed) / 2.0) * 2.0 + placed + 2.0 * dither) * step
        offset = np.clip(offset + target - cells, -step, step)
    if not lossless:
        return marked
    native = layoutMask(mask, height, width, float(opts.get("scale", 40.0)), str(opts.get("placement", "center")))
    return Image.fromarray((np.asarray(marked) & 0xFE) | native[..., None].astype(np.uint8))


def boxBlur(arr: np.ndarray) -> np.ndarray:
    pad = np.pad(arr, 1, mode="edge")
    total = pad.cumsum(0).cumsum(1)
    total = np.pad(total, ((1, 0), (1, 0)))
    return (total[3:, 3:] - total[:-3, 3:] - total[3:, :-3] + total[:-3, :-3]) / 9.0


def readBitPlane(arr: np.ndarray) -> Optional[np.ndarray]:
    """Returns the native mark if bit 0 is a coherent image shared by all channels. Only called after the cell layer
    is confirmed, because flat graphics also have coherent low bits."""
    bits = arr & 1
    if (bits[..., 0] == bits[..., 1]).mean() < 0.99 or (bits[..., 0] == bits[..., 2]).mean() < 0.99:
        return None
    plane = bits[..., 0].astype(bool)
    agreement = (float((plane[1:] == plane[:-1]).mean()) + float((plane[:, 1:] == plane[:, :-1]).mean())) / 2.0
    return plane if agreement >= 0.9 else None


def analyzeMark(rawBytes: bytes) -> Dict[str, Any]:
    """Blind read. Tries every strength: the right one gives a coherent shape, an unmarked photo gives coin flips."""
    with Image.open(io.BytesIO(rawBytes)) as im:
        rgb = im.convert("RGB")
    gray = rgb.convert("L")
    best, bestBits = 0.5, np.zeros((GRID_CHOICES[0], GRID_CHOICES[0]), dtype=np.int64)
    # The grid is tried too, so a photo resized after marking is still read.
    for gridShort in GRID_CHOICES:
        gridH, gridW = gridShape(*gray.size, gridShort)
        sign, dither = cellKeys(gridH, gridW)
        cells = readCells(gray, gridH, gridW, sign)
        for step in range(1, MAX_STRENGTH + 1):
            bits = cellBits(cells, dither, float(step))
            agreement = (float((bits[1:] == bits[:-1]).mean()) + float((bits[:, 1:] == bits[:, :-1]).mean())) / 2.0
            if agreement > best:
                best, bestBits = agreement, bits
    # Cleanup would erase thin strokes, so it runs only when the read is damaged.
    shape = bestBits > 0 if best >= 0.9 else boxBlur(bestBits.astype(np.float64)) > 0.5
    coverage = float(shape.mean())
    found = best >= MIN_AGREEMENT and 0.0005 < coverage < 0.98
    res: Dict[str, Any] = {"markFound": found, "markScore": round(best * 100.0, 1), "markLsb": False}
    if found:
        native = readBitPlane(np.asarray(rgb))
        res["markLsb"] = native is not None
        shape = shape if native is None else native
        res.update({"markCoverage": round(float(shape.mean()) * 100.0, 2), "markPng": toB64Png(shape)})
    return res


def inspectStego(rawBytes: bytes) -> Dict[str, Any]:
    """Runs every decoder: the visual mark first, then the text frame and metadata readers."""
    res = extractSteganographyPil(rawBytes)
    try:
        res.update(analyzeMark(rawBytes))
    except Exception as exc:
        res.update({"markFound": False, "markError": str(exc)})
    if res.get("markFound"):
        layer = "LSB Bit Plane + Hidden Mark" if res.get("markLsb") else "Hidden Mark"
        res["method"] = layer + (f" + {res['method']}" if res.get("found") else "")
        res["found"] = True
    return res
