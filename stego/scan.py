"""Scanner for hidden data and watermarks that Lumiya did not write.

Each finding says what was measured. Blind detection has limits: encrypted or keyed schemes (steghide, SynthID,
Tree-Ring, Stable Signature, RivaGAN) need their key or model and are not claimed here.
"""
from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image

_MAGIC = (
    (b"PK\x03\x04", "ZIP archive"), (b"%PDF", "PDF document"), (b"\x89PNG", "PNG image"), (b"\xff\xd8\xff", "JPEG image"),
    (b"Rar!", "RAR archive"), (b"7z\xbc\xaf", "7-Zip archive"), (b"GIF8", "GIF image"), (b"\x1f\x8b", "GZIP data"),
    (b"BZh", "BZIP2 data"), (b"RIFF", "RIFF media"), (b"ID3", "MP3 audio"), (b"\x00\x00\x00 ftyp", "MP4 media"),
)
_TEXT_RUN = re.compile(rb"[\x20-\x7e\t\r\n]{24,}")
# A JPEG scan ends at the first 0xFF that is not byte stuffing (FF00) or a restart marker (FFD0-FFD7).
_SCAN_END = re.compile(rb"\xff(?!\x00|[\xd0-\xd7])")

# invisible-watermark (imwatermark) payloads written by Stable Diffusion releases.
_KNOWN_DWT = {
    "Stable Diffusion v1 (\"StableDiffusionV1\")": np.unpackbits(np.frombuffer(b"StableDiffusionV1", np.uint8)),
    "Stable Diffusion v2 (\"SDV2\")": np.unpackbits(np.frombuffer(b"SDV2", np.uint8)),
    "Stable Diffusion XL / diffusers": np.array([int(c) for c in bin(0b101100111110110010010000011110111011000110011110)[2:]], np.uint8),
}
_DWT_SCALE = 36.0
_DWT_MAX_BLOCKS = 250_000


def _finding(kind: str, name: str, detail: str, confidence: str) -> Dict[str, str]:
    return {"kind": kind, "name": name, "detail": detail, "confidence": confidence}


def _describe(blob: bytes) -> str:
    for magic, label in _MAGIC:
        if blob.startswith(magic):
            return label
    text = blob[:80]
    if text and all(32 <= c < 127 or c in (9, 10, 13) for c in text):
        return f"text \"{text.decode('ascii').strip()[:60]}\""
    return "unknown binary data"


def _trailingOffset(raw: bytes) -> Optional[int]:
    """Byte offset where the image format says the file ends, or None if the format is not walked."""
    if raw[:2] == b"\xff\xd8":
        i, n = 2, len(raw)
        while i + 4 <= n:
            if raw[i] != 0xFF:
                return None
            m = raw[i + 1]
            if m == 0xFF:
                i += 1
                continue
            if m == 0xD9:
                return i + 2
            if 0xD0 <= m <= 0xD7 or m == 0x01:
                i += 2
                continue
            i += 2 + int.from_bytes(raw[i + 2:i + 4], "big")
            if m == 0xDA:
                hit = _SCAN_END.search(raw, i)
                if not hit:
                    return None
                i = hit.start()
        return None
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        i = 8
        while i + 8 <= len(raw):
            length = int.from_bytes(raw[i:i + 4], "big")
            if raw[i + 4:i + 8] == b"IEND":
                return i + 12 + length
            i += 12 + length
        return None
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return 8 + int.from_bytes(raw[4:8], "little")
    return None


def scanContainer(raw: bytes, im: Any) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    end = _trailingOffset(raw)
    if end is not None and end < len(raw):
        tail = raw[end:]
        # Declared extras are not hidden: MPF secondary images (Ultra HDR gain map, depth) and Samsung's SEFT trailer.
        if b"MPF\x00" in raw[:end]:
            while tail[:2] == b"\xff\xd8" and (nxt := _trailingOffset(tail)):
                tail = tail[nxt:]
        if tail.endswith(b"SEFT"):
            tail = b""
        if tail.strip(b"\x00\r\n \xff"):
            what = _describe(tail.lstrip(b"\x00"))
            out.append(_finding("appended", "Data after end of image", f"{len(tail):,} bytes after the image ends: {what}.", "certain"))
    if b"jumb" in raw and b"c2pa" in raw:
        out.append(_finding("provenance", "C2PA Content Credentials", "A C2PA manifest (JUMBF box) is embedded. Its signature is not verified here.", "certain"))
    if b"trainedAlgorithmicMedia" in raw:
        made = b"compositeWithTrainedAlgorithmicMedia" in raw and b"/trainedAlgorithmicMedia" not in raw
        out.append(_finding("provenance", "IPTC AI source label", "XMP marks the image as " + ("edited with" if made else "made by") + " generative AI (IPTC DigitalSourceType).", "certain"))
    info = getattr(im, "info", {}) or {}
    texts = {k: v for k, v in info.items() if isinstance(v, (str, bytes))}
    try:
        userComment = im.getexif().get_ifd(0x8769).get(0x9286)
        if userComment:
            texts["EXIF UserComment"] = userComment
    except Exception:
        pass
    for key, val in texts.items():
        s = val.decode("utf-8", "replace") if isinstance(val, bytes) else val
        if key in ("prompt", "workflow") and "class_type" in s:
            out.append(_finding("generator", "ComfyUI workflow", f"A ComfyUI generation graph is stored in the '{key}' text field.", "certain"))
        elif "Steps:" in s and "Sampler:" in s:
            out.append(_finding("generator", "Stable Diffusion WebUI parameters", f"Generation settings are stored in '{key}': {s[:120].strip()}...", "certain"))
    return out


def _lsbBytes(arr: np.ndarray, bits: int, lsbFirst: bool, limit: int = 1 << 16) -> bytes:
    flat = arr.reshape(-1)[: limit * 8 // bits]
    if bits == 1:
        stream = flat & 1
    else:
        stream = np.stack([(flat >> 1) & 1, flat & 1], axis=1).reshape(-1)
    stream = stream[: stream.size // 8 * 8].astype(np.uint8)
    return np.packbits(stream, bitorder="little" if lsbFirst else "big").tobytes()


def scanLsbText(rgb: np.ndarray) -> List[Dict[str, str]]:
    """zsteg-style read of plain payloads: bit planes 0 and 0-1, RGB and single channels, both bit orders."""
    out: List[Dict[str, str]] = []
    planes = {"RGB": rgb, "R": rgb[..., 0], "G": rgb[..., 1], "B": rgb[..., 2]}
    for chName, arr in planes.items():
        for bits in (1, 2):
            for lsbFirst in (False, True):
                data = _lsbBytes(arr, bits, lsbFirst)
                where = f"bit {'0' if bits == 1 else '0-1'}, {chName}, {'LSB' if lsbFirst else 'MSB'}-first"
                for magic, label in _MAGIC:
                    if data.startswith(magic):
                        out.append(_finding("lsb", f"Hidden {label} in pixel bits", f"A {label} header starts the {where} stream.", "high"))
                for m in _TEXT_RUN.finditer(data):
                    text = m.group().decode("ascii")
                    # Flat areas read as repeats like "UUUU" (bits 0101); real text uses many characters, none dominating.
                    if "LUMIYA::" in text or len(set(text)) < 10 or max(text.count(ch) for ch in set(text)) > 0.25 * len(text):
                        continue
                    out.append(_finding("lsb", "Hidden text in pixel bits", f"{where} at byte {m.start()}: \"{text.strip()[:100]}\"", "high"))
                    break
                if len(out) >= 4:
                    return out
    return out


def rsEstimate(channel: np.ndarray) -> Optional[float]:
    """RS steganalysis (Fridrich, Goljan, Du 2001): estimated fraction of pixels whose LSB was replaced."""
    x = channel[:, : channel.shape[1] // 4 * 4].astype(np.int16).reshape(-1, 4)
    if len(x) < 2000:
        return None
    mask = np.array([False, True, True, False])

    def counts(g):
        base = np.abs(np.diff(g, axis=1)).sum(1)
        pos, neg = g.copy(), g.copy()
        pos[:, mask] ^= 1
        neg[:, mask] = ((neg[:, mask] + 1) ^ 1) - 1
        fp, fn = np.abs(np.diff(pos, axis=1)).sum(1), np.abs(np.diff(neg, axis=1)).sum(1)
        n = float(len(g))
        return (fp > base).sum() / n, (fp < base).sum() / n, (fn > base).sum() / n, (fn < base).sum() / n

    rm, sm, rn, sn = counts(x)
    if rm + sm < 0.1:
        return None  # flat or saturated: almost no group changes, the estimate means nothing
    rm1, sm1, rn1, sn1 = counts(x ^ 1)
    d0, d1, dn0, dn1 = rm - sm, rm1 - sm1, rn - sn, rn1 - sn1
    a, b, c = 2 * (d1 + d0), dn0 - dn1 - d1 - 3 * d0, d0 - dn0
    if abs(a) < 1e-9:
        if abs(b) < 1e-9:
            return None
        z = -c / b
    else:
        disc = b * b - 4 * a * c
        if disc < 0:
            return None
        z = min(((-b + disc ** 0.5) / (2 * a), (-b - disc ** 0.5) / (2 * a)), key=abs)
    if abs(z - 0.5) < 1e-9:
        return None
    return float(np.clip(z / (z - 0.5), 0.0, 1.0))


def scanLsbStatistics(rgb: np.ndarray) -> List[Dict[str, str]]:
    step = max(1, rgb.shape[0] // 1500)
    sample = rgb[::step]
    whole = [rsEstimate(sample[..., c]) for c in range(3)]
    band = [rsEstimate(rgb[: max(64, rgb.shape[0] // 8), :, c]) for c in range(3)]
    whole = [v for v in whole if v is not None]
    band = [v for v in band if v is not None]
    w = float(np.median(whole)) if whole else 0.0
    t = float(np.median(band)) if band else 0.0
    note = " Added pixel noise (for example adversarial protection, including Lumiya's) looks the same to this test."
    if w >= 0.12:
        return [_finding("lsb", "Randomised LSBs (statistical)", f"RS analysis estimates about {w * 100:.0f}% of pixel LSBs were replaced across the image, as LSB embedding does." + note, "medium")]
    if t >= 0.25:
        return [_finding("lsb", "Randomised LSBs in top rows (statistical)", f"RS analysis estimates about {t * 100:.0f}% of LSBs replaced in the top eighth of the image, where sequential tools write first." + note, "medium")]
    return []


def _dwtScores(rgb: np.ndarray):
    """Per-block bit reads of the invisible-watermark dwtDct and dwtDctSvd methods (U channel, Haar LL, 4x4 blocks)."""
    h, w = rgb.shape[0] // 4 * 4, rgb.shape[1] // 4 * 4
    f = rgb[:h, :w].astype(np.float64)
    y = 0.299 * f[..., 0] + 0.587 * f[..., 1] + 0.114 * f[..., 2]
    u = np.clip(np.rint(0.492 * (f[..., 2] - y) + 128.0), 0, 255)
    ll = (u[0::2, 0::2] + u[0::2, 1::2] + u[1::2, 0::2] + u[1::2, 1::2]) / 2.0
    bh, bw = ll.shape[0] // 4, ll.shape[1] // 4
    rows = max(1, min(bh, _DWT_MAX_BLOCKS // max(1, bw)))  # keep whole leading rows so block numbering is unchanged
    blocks = ll[: rows * 4, : bw * 4].reshape(rows, 4, bw, 4).transpose(0, 2, 1, 3).reshape(-1, 16)
    pos = np.argmax(np.abs(blocks[:, 1:]), axis=1) + 1
    val = np.abs(blocks[np.arange(len(blocks)), pos])
    s0 = np.linalg.svd(blocks.reshape(-1, 4, 4), compute_uv=False)[:, 0]
    return {"dwtDct": (val % _DWT_SCALE) > _DWT_SCALE / 2, "dwtDctSvd": (s0 % _DWT_SCALE) > _DWT_SCALE / 2}, bw


def _bitsFor(scores: np.ndarray, length: int):
    idx = np.arange(scores.size) % length
    avg = np.bincount(idx, scores.astype(np.float64), length) / np.bincount(idx, minlength=length)
    n = scores.size / length
    dist = float(np.abs(avg - 0.5).mean())
    # Relative to what unmarked (coin-flip) blocks would give; 0 when the bits are not decisive in absolute terms,
    # because a length that matches the blocks per row turns ordinary vertical image structure into "repeats".
    consistency = dist / (0.5 / np.sqrt(n) * 0.798) if dist >= 0.3 else 0.0
    return avg * 255 > 127, consistency


def scanInvisibleWatermark(rgb: np.ndarray) -> List[Dict[str, str]]:
    if rgb.shape[0] * rgb.shape[1] < 256 * 256:
        return []
    out: List[Dict[str, str]] = []
    scoreSets, bw = _dwtScores(rgb)
    for method, scores in scoreSets.items():
        if not 0.1 < scores.mean() < 0.9:
            continue  # near-grey image: every block reads the same, nothing to decode
        for name, ref in _KNOWN_DWT.items():
            bits, cons = _bitsFor(scores, ref.size)
            match = float((bits == ref.astype(bool)).mean())
            if match >= 0.9 and cons >= 2.0 and 0.1 < bits.mean() < 0.9:
                out.append(_finding("watermark", f"invisible-watermark: {name}", f"{method} payload matches {match * 100:.0f}% of the {ref.size} bits.", "high" if match >= 0.97 else "medium"))
        if out:
            return out
        def agree(lag):
            return float((scores[:-lag] == scores[lag:]).mean()) if 0 < lag < scores.size else 1.0

        # A real payload makes blocks one period apart agree far more than neighbours do; image structure (flat
        # areas, vertical edges) makes the next block and the block below agree just as much.
        neighbour = max(agree(1), agree(bw))
        tried = [(L, *_bitsFor(scores, L)) for L in (32, 40, 48, 56, 64, 96, 128, 136, 160, 192, 256) if bw % L and L % bw]
        best = max([c for _, _, c in tried] or [0.0])
        for L, bits, cons in tried:
            if cons >= 6.0 and cons >= 0.8 * best and 0.1 < bits.mean() < 0.9 and agree(L) - neighbour >= 0.2:
                payload = np.packbits(bits.astype(np.uint8)).tobytes()
                text = payload.decode("ascii") if all(32 <= c < 127 for c in payload) else payload.hex()
                out.append(_finding("watermark", "invisible-watermark (unknown payload)", f"{method}, {L}-bit payload repeats consistently ({cons:.0f}x chance): {text}", "medium"))
                return out
    return out


def scanForeign(raw: bytes, lumiyaLsb: bool = False) -> List[Dict[str, str]]:
    """Every non-Lumiya detector. LSB statistics are skipped when a Lumiya LSB layer already explains them."""
    with Image.open(io.BytesIO(raw)) as im:
        out = scanContainer(raw, im)
        lossless = im.format in ("PNG", "BMP", "TIFF", "TGA", "PPM") or (im.format == "WEBP" and b"VP8L" in raw[:64])
        rgb = np.asarray(im.convert("RGB"))
    out += scanLsbText(rgb)
    # LSB payloads cannot survive lossy compression, and decoded JPEGs give RS false positives.
    if lossless and not lumiyaLsb and not any(f["kind"] == "lsb" for f in out):
        out += scanLsbStatistics(rgb)
    out += scanInvisibleWatermark(rgb)
    return out
