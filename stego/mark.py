"""Hidden visual mark (v2) + binary LSB steganography.

Every marked file carries a QIM cell layer: fixed-size cells whose key repeats every KEY_PERIOD cells, plus a faint
sync pattern on the same tile. The reader recovers scale (autocorrelation, then drift refinement) and crop offset
(fold + correlate) before reading the cells, so the mark survives JPEG, resizing and cropping.
Lossless files also carry the mark at native resolution in bit 0 of every RGB channel.
Invisible Binary Text mode ('binary') embeds UTF-8 into the top LSB scanlines + container metadata.
Marks written before v2 are not read (dropped during the pilot).
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
from stego.scan import scanForeign

MAX_MARK_SIDE = 2000
# Mark v2: cells have a fixed pixel size and the key repeats every KEY_PERIOD cells, so any crop still holds whole
# key tiles. A faint sync pattern on the same tile lets the reader recover scale (autocorrelation) and offset (fold +
# correlate) before reading the cells.
KEY_PERIOD = 32
CANON_CELL = 8
CANON_TILE = KEY_PERIOD * CANON_CELL
CARRIER_SEED = 0x4C4D59
SYNC_SEED = 0x4C4D5932
MAX_STRENGTH = 16
MIN_AGREEMENT = 0.68
MIN_SYNC_PEAK = 7.0
# Cells are 6-48 px when marked and may later be scaled 0.25x-2x, so the canonical rescale factor stays in this range.
R_RANGE = (CANON_CELL / 96.0, CANON_CELL / 1.5)
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


def cellSize(width: int, height: int) -> int:
    """Even cell size in pixels, about 1/320 of the short side and 6-24 px: big enough to survive compression, small enough that the reader sees several key tiles."""
    return min(24, max(6, int(round(min(width, height) / 640.0)) * 2))


def _tiled(tile: np.ndarray, h: int, w: int) -> np.ndarray:
    reps = (-(-h // tile.shape[0]), -(-w // tile.shape[1]))
    return np.tile(tile, reps)[:h, :w]


def cellKeys(cellsH: int, cellsW: int) -> Tuple[np.ndarray, np.ndarray]:
    """Per-cell sign and dither: one KEY_PERIOD tile repeated, so the key at any cell depends only on its tile phase."""
    rng = np.random.default_rng(CARRIER_SEED)
    sign = rng.choice((-1.0, 1.0), size=(KEY_PERIOD, KEY_PERIOD))
    dither = rng.random((KEY_PERIOD, KEY_PERIOD))
    return _tiled(sign, cellsH, cellsW), _tiled(dither, cellsH, cellsW)


def syncHalfCells(h2: int, w2: int) -> np.ndarray:
    """+-1 sync pattern on the half-cell grid, one tile repeated."""
    tile = np.random.default_rng(SYNC_SEED).choice((-1.0, 1.0), size=(2 * KEY_PERIOD, 2 * KEY_PERIOD))
    return _tiled(tile, h2, w2)


def _expand(halfCells: np.ndarray, px: int) -> np.ndarray:
    return np.repeat(np.repeat(halfCells, px, axis=0), px, axis=1)


def quadPattern(sign: np.ndarray) -> np.ndarray:
    """Expands each cell into a signed 2x2 checker on a grid twice as fine."""
    pattern = np.repeat(np.repeat(sign, 2, axis=0), 2, axis=1)
    pattern[0::2, 1::2] *= -1
    pattern[1::2, 0::2] *= -1
    return pattern


def readCells(gray: np.ndarray, cell: int, sign: np.ndarray) -> np.ndarray:
    """Signed checker mean of each cell; `gray` starts on a cell (and key tile) boundary."""
    cellsH, cellsW = sign.shape
    q = _expand(quadPattern(sign), cell // 2)
    g = gray[: cellsH * cell, : cellsW * cell] * q
    return g.reshape(cellsH, cell, cellsW, cell).mean(axis=(1, 3))


def cellBits(cells: np.ndarray, dither: np.ndarray, step: float) -> np.ndarray:
    return np.rint(cells / step - 2.0 * dither).astype(np.int64) % 2


V1_GRIDS = (128, 192, 256, 384, 512)


def _readV1(gray: Any) -> Tuple[float, np.ndarray]:
    """Read-only support for marks written before v2: whole-photo grids, no crop resync. Nothing writes v1 any more."""
    best, bestBits = 0.5, np.zeros((V1_GRIDS[0], V1_GRIDS[0]), dtype=np.int64)
    short = max(1, min(gray.size))
    for gridShort in V1_GRIDS:
        gridH, gridW = max(8, round(gridShort * gray.size[1] / short)), max(8, round(gridShort * gray.size[0] / short))
        rng = np.random.default_rng(CARRIER_SEED)
        side = max(gridH, gridW)
        sign = rng.choice((-1.0, 1.0), size=(side, side))[:gridH, :gridW]
        dither = rng.random((side, side))[:gridH, :gridW]
        small = np.asarray(gray.resize((gridW * 2, gridH * 2), Image.Resampling.BOX), dtype=np.float64)
        cells = (small * quadPattern(sign)).reshape(gridH, 2, gridW, 2).mean(axis=(1, 3))
        for step in range(1, MAX_STRENGTH + 1):
            bits = cellBits(cells, dither, float(step))
            agreement = (float((bits[1:] == bits[:-1]).mean()) + float((bits[:, 1:] == bits[:, :-1]).mean())) / 2.0
            if agreement > best:
                best, bestBits = agreement, bits
    return best, bestBits


def _highPass(g: np.ndarray) -> np.ndarray:
    return g - boxBlur(g)


def _foldCorr(g: np.ndarray) -> Tuple[float, int, int]:
    """Folds every whole tile of a canonical image onto one and correlates it with the sync tile.
    Returns (peak strength in std units, dy, dx) where the key tile starts at (dy, dx) of this array."""
    ny, nx = g.shape[0] // CANON_TILE, g.shape[1] // CANON_TILE
    if ny < 1 or nx < 1:
        return 0.0, 0, 0
    # Folding and the high-pass are both linear, so filtering the one folded tile equals filtering the whole image.
    folded = _highPass(g[: ny * CANON_TILE, : nx * CANON_TILE].reshape(ny, CANON_TILE, nx, CANON_TILE).sum(axis=(0, 2)))
    sync = _expand(syncHalfCells(2 * KEY_PERIOD, 2 * KEY_PERIOD), CANON_CELL // 2)
    corr = np.fft.irfft2(np.fft.rfft2(folded) * np.conj(np.fft.rfft2(sync)), s=folded.shape)
    dy, dx = np.unravel_index(int(np.argmax(corr)), corr.shape)
    return float((corr.max() - corr.mean()) / max(corr.std(), 1e-12)), int(dy), int(dx)


def _canon(gray: Any, r: float) -> np.ndarray:
    w, h = gray.size
    return np.asarray(gray.resize((max(1, round(w * r)), max(1, round(h * r))), Image.Resampling.BILINEAR), dtype=np.float64)


def _wrap(d: int) -> int:
    return (d + CANON_TILE // 2) % CANON_TILE - CANON_TILE // 2


def _refineScale(hp: np.ndarray) -> float:
    """Relative scale error from drift: with a slightly wrong scale the tile offset creeps across the photo, so the
    offset measured in two halves differs by error x distance. Returns the factor to multiply r by."""
    h, w = hp.shape
    slopes = []
    if w >= 4 * CANON_TILE:
        _, _, xl = _foldCorr(hp[:, : w // 2])
        _, _, xr = _foldCorr(hp[:, w // 2:])
        slopes.append(_wrap(xr + w // 2 - xl) / (w / 2.0))
    if h >= 4 * CANON_TILE:
        _, yt, _ = _foldCorr(hp[: h // 2])
        _, yb, _ = _foldCorr(hp[h // 2:])
        slopes.append(_wrap(yb + h // 2 - yt) / (h / 2.0))
    return 1.0 / (1.0 + float(np.mean(slopes))) if slopes else 1.0


def findSync(gray: Any) -> Tuple[float, float, int, int, np.ndarray]:
    """Recovers how the photo was scaled and cropped since marking. Returns (peak, r, dy, dx, canonical gray):
    r rescales the photo to CANON_CELL cells, and the key tile starts at (dy, dx) in that rescaled image."""
    w, h = gray.size
    # Tile size from a full-resolution central window: shrinking the photo instead would blur the fine sync pattern away.
    ds = 1.0
    side = min(w, h, 2560)
    cx, cy = (w - side) // 2, (h - side) // 2
    hp = _highPass(np.asarray(gray.crop((cx, cy, cx + side, cy + side)), dtype=np.float64))
    hp -= hp.mean()
    ac = np.fft.irfft2(np.abs(np.fft.rfft2(hp)) ** 2, s=hp.shape)
    ac /= max(ac[0, 0], 1e-12)
    lo = int(CANON_TILE / R_RANGE[1])
    hi = min(int(CANON_TILE / R_RANGE[0]), min(hp.shape) // 2)
    # The unresized guess comes first: it is the common case, and the only option when the photo holds a single tile.
    hint = CANON_TILE / (KEY_PERIOD * cellSize(w, h))
    cands: list = [CANON_TILE * ds / hint]
    if hi > lo + 8:
        score = ac[0, lo:hi] + ac[lo:hi, 0]
        # The tile shows as a sharp spike; subtracting the local trend removes the smooth falloff of natural texture.
        score = score - np.convolve(score, np.ones(15) / 15.0, mode="same")
        cands += [lo + int(i) for i in np.argsort(score)[::-1][:6]]
    bestPeak, bestR = 0.0, 1.0
    seen = set()
    for lag in cands:
        if lag in seen:
            continue
        seen.update((lag - 1, lag, lag + 1))
        r0 = CANON_TILE * ds / lag
        if not R_RANGE[0] <= r0 <= R_RANGE[1]:
            continue
        # Search on a central region about five tiles wide: cheap, and short enough that a small scale error barely drifts.
        side = int(5 * CANON_TILE / r0)
        cx, cy = max(0, (w - side) // 2), max(0, (h - side) // 2)
        region = gray.crop((cx, cy, min(w, cx + side), min(h, cy + side)))
        for k in range(-4, 5):
            r = r0 * (1.0 + 0.003 * k)
            peak = _foldCorr(_canon(region, r))[0]
            if peak > bestPeak:
                bestPeak, bestR = peak, r
        if bestPeak >= 3 * MIN_SYNC_PEAK:
            break
    if bestPeak <= 0.0:
        return 0.0, 1.0, 0, 0, np.zeros((1, 1))
    for attempt in range(3):
        g2 = _canon(gray, bestR)
        fix = _refineScale(g2)
        if abs(fix - 1.0) < 2e-4 or attempt == 2:
            break
        bestR *= min(1.05, max(0.95, fix))
    peak, dy, dx = _foldCorr(g2)
    return peak, bestR, dy, dx, g2


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
    cell = cellSize(width, height)
    cellsH, cellsW = max(1, height // cell), max(1, width // cell)
    scalePct = float(cfg.get("scale", 40.0))
    placeStr = str(cfg.get("placement", "center"))
    placed = layoutMask(mask, cellsH, cellsW, scalePct, placeStr)
    step = max(1.0, min(float(MAX_STRENGTH), round(float(cfg.get("strength", 4.0)))))
    sign, dither = cellKeys(cellsH, cellsW)
    quad = quadPattern(sign)
    half = cell // 2
    sync = _expand(syncHalfCells(2 * cellsH, 2 * cellsW), half) * max(1.0, step / 4.0)
    base = np.asarray(rgbImg.convert("RGB"), dtype=np.float32)
    offset = np.zeros((cellsH, cellsW))
    full = np.zeros((height, width), dtype=np.float32)
    for _ in range(4):
        carrier = _expand(quad * np.repeat(np.repeat(offset, 2, 0), 2, 1), half) + sync
        # Strength is the hard per-pixel limit for carrier and sync together.
        full[: cellsH * cell, : cellsW * cell] = np.clip(carrier, -step, step)[:height, :width]
        marked = Image.fromarray(np.clip(np.rint(base + full[..., None]), 0, 255).astype(np.uint8))
        cells = readCells(np.asarray(marked.convert("L"), dtype=np.float64), cell, sign)
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
            rgb = ImageOps.exif_transpose(im).convert("RGB")
    width, height = rgb.size
    rgbArr = np.asarray(rgb)

    binRes = extractSteganographyPil(rawBytes)
    binFound = bool(binRes.get("found"))

    # 1. QIM cell recovery after re-synchronising scale and crop offset; survives JPEG, resizing and cropping
    gray = rgb.convert("L")
    syncPeak, r, dy, dx, g2 = findSync(gray)
    best, bestBits = 0.5, np.zeros((KEY_PERIOD, KEY_PERIOD), dtype=np.int64)
    aligned = g2[dy:, dx:]
    cellsH, cellsW = aligned.shape[0] // CANON_CELL, aligned.shape[1] // CANON_CELL
    if syncPeak >= MIN_SYNC_PEAK and cellsH >= 8 and cellsW >= 8:
        sign, dither = cellKeys(cellsH, cellsW)
        cells = readCells(aligned, CANON_CELL, sign)
        for step in range(1, MAX_STRENGTH + 1):
            bits = cellBits(cells, dither, float(step))
            agreement = (float((bits[1:] == bits[:-1]).mean()) + float((bits[:, 1:] == bits[:, :-1]).mean())) / 2.0
            if agreement > best:
                best, bestBits = agreement, bits

    shape = bestBits > 0 if best >= 0.9 else boxBlur(bestBits.astype(np.float64)) > 0.5
    coverage = float(shape.mean())
    found = best >= MIN_AGREEMENT and 0.0005 < coverage < 0.98
    v1 = False
    if not found:
        v1Best, v1Bits = _readV1(gray)
        v1Shape = v1Bits > 0 if v1Best >= 0.9 else boxBlur(v1Bits.astype(np.float64)) > 0.5
        if v1Best >= MIN_AGREEMENT and 0.0005 < float(v1Shape.mean()) < 0.98:
            v1, found, best, shape = True, True, v1Best, v1Shape

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
        "method": (("QIM Cell Mark (v1)" if v1 else "QIM Cell Mark") + (f" + {binRes.get('method')}" if binFound else "")) if found else binRes.get("method", "None"),
    }
    if v1:
        gridH, gridW = shape.shape
        rawBox = computeMaskBBox(shape)
        sx, sy = width / gridW, height / gridH
        bbox = {"x": int(rawBox["x"] * sx), "y": int(rawBox["y"] * sy), "w": int(rawBox["w"] * sx), "h": int(rawBox["h"] * sy)} if rawBox else None
        res.update({"markCoverage": round(float(shape.mean()) * 100.0, 2), "markPng": toB64Png(shape), "markBBox": bbox, "markResolution": f"{gridW}x{gridH} (QIM v1 grid)"})
    elif found:
        # Put the shape back where it sits in the whole photo: the read started at the key tile (dy, dx).
        canvas = np.zeros(g2.shape, dtype=np.uint8)
        px = _expand(shape.astype(np.uint8) * 255, CANON_CELL // 2 * 2)[: canvas.shape[0] - dy, : canvas.shape[1] - dx]
        canvas[dy:dy + px.shape[0], dx:dx + px.shape[1]] = px
        gridW, gridH = max(1, g2.shape[1] // CANON_CELL), max(1, g2.shape[0] // CANON_CELL)
        shape = np.asarray(Image.fromarray(canvas).resize((gridW, gridH), Image.Resampling.BOX)) > 127
        rawBox = computeMaskBBox(shape)
        sx, sy = width / gridW, height / gridH
        bbox = {"x": int(rawBox["x"] * sx), "y": int(rawBox["y"] * sy), "w": int(rawBox["w"] * sx), "h": int(rawBox["h"] * sy)} if rawBox else None
        res.update(
            {
                "markCoverage": round(float(shape.mean()) * 100.0, 2),
                "markPng": toB64Png(shape),
                "markBBox": bbox,
                "markResolution": f"{gridW}x{gridH} (QIM v2 grid, sync {syncPeak:.0f})",
            }
        )
    return res


def inspectStego(rawBytes: bytes, foreign: bool = True) -> Dict[str, Any]:
    """Runs every decoder: the Lumiya readers (LSB frame, QIM mark v2 and v1, bit plane) and the scanner for
    hidden data and watermarks other tools wrote. `found` stays Lumiya-only; other findings are in `foreign`."""
    try:
        res = analyzeMark(rawBytes)
    except Exception as exc:
        res = extractSteganographyPil(rawBytes)
        res.update({"markFound": False, "markError": str(exc)})
    if not foreign:
        return res
    try:
        res["foreign"] = scanForeign(rawBytes, lumiyaLsb=bool(res.get("binaryFound") or res.get("markLsb")))
    except Exception as exc:
        res["foreign"], res["foreignError"] = [], str(exc)
    return res
