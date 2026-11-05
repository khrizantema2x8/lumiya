"""Steganography service: embeds and reads the Lumiya LSB binary frame. Independent of the algo plugins."""
from __future__ import annotations

import io
import math
from typing import Any, Dict

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore


def buildLmy1Frame(secretMessage: str) -> bytes:
    """Packs UTF-8 message into a self-synchronizing LMY1 binary frame."""
    msgBytes = secretMessage.encode("utf-8")[:32767]
    bodyBytes = f"[LUMIYA::{secretMessage}]".encode("utf-8")
    return b"LMY1" + len(msgBytes).to_bytes(2, "big") + msgBytes + b"::" + bodyBytes


def applySteganographyPil(pilImg: Any, secretMessage: str, cyclic: bool = False) -> Any:
    """Embeds a 2-bit LSB UTF-8 frame across RGB channels.
    When cyclic=False (default for Invisible Binary Text mode), writes strictly into the top scanlines
    needed for the frame (repeated 4x for resilience) so the rest of the image bit-plane stays untouched
    and the exact scanline bounding box can be highlighted in Inspect.
    """
    rgbImg = pilImg.convert("RGB")
    if not secretMessage or not secretMessage.strip():
        return rgbImg
    frameBytes = buildLmy1Frame(secretMessage)
    pairs = [(byteVal >> shift) & 3 for byteVal in frameBytes for shift in (6, 4, 2, 0)]
    if not pairs:
        return rgbImg

    totalPairs = len(pairs)
    arr = np.array(rgbImg, dtype=np.uint8)
    h, w, c = arr.shape
    flat = arr.reshape(-1)
    pairsArr = np.array(pairs, dtype=np.uint8)

    if cyclic:
        idx = np.arange(flat.size)
        flat = (flat & 0xFC) | pairsArr[idx % totalPairs]
    else:
        # Embed 4 copies of the frame in the top scanlines for robustness without polluting the whole canvas
        span = min(flat.size, max(totalPairs * 4, w * c))
        idx = np.arange(span)
        flat[:span] = (flat[:span] & 0xFC) | pairsArr[idx % totalPairs]

    return Image.fromarray(flat.reshape(h, w, c))


def extractSteganographyPil(rawBytes: bytes) -> Dict[str, Any]:
    """Extracts and verifies embedded Lumiya steganographic payload from image pixels or container metadata."""
    if Image is None or not rawBytes:
        return {"found": False, "message": "", "method": "Unavailable"}
    try:
        with Image.open(io.BytesIO(rawBytes)) as im:
            width, height = im.size
            metaText = im.info.get("LumiyaStego") or im.info.get("comment")
            if isinstance(metaText, bytes):
                metaText = metaText.decode("utf-8", errors="replace")

            rgb = im.convert("RGB")
            flat = np.array(rgb, dtype=np.uint8).reshape(-1)
            maxPairs = min(flat.size, 65536 * 4)
            pairs = flat[:maxPairs] & 3
            bArr = (
                (pairs[0::4] << 6)
                | (pairs[1::4] << 4)
                | (pairs[2::4] << 2)
                | pairs[3::4]
            )
            stream = bArr.tobytes()

            idx = stream.find(b"LMY1")
            if idx != -1 and idx + 6 <= len(stream):
                msgLen = int.from_bytes(stream[idx + 4 : idx + 6], "big")
                if 0 < msgLen <= 32767 and idx + 6 + msgLen <= len(stream):
                    msg = stream[idx + 6 : idx + 6 + msgLen].decode("utf-8", errors="replace")
                    frameBytesLen = len(buildLmy1Frame(msg))
                    totalChannelsUsed = min(flat.size, max(frameBytesLen * 4 * 4, width * 3))
                    scanlines = max(1, min(height, math.ceil(totalChannelsUsed / max(1, width * 3))))
                    return {
                        "found": True,
                        "binaryFound": True,
                        "message": msg,
                        "rawFrame": f"[LUMIYA::{msg}]",
                        "method": "2-Bit RGB LSB Binary Stream (LMY1)",
                        "bitPlane": "LSB Bit-Planes 0 & 1 (RGB)",
                        "scanlines": scanlines,
                        "bbox": {
                            "x": 0,
                            "y": 0,
                            "w": width,
                            "h": scanlines,
                        },
                    }

            lmyIdx = stream.find(b"[LUMIYA::")
            if lmyIdx != -1:
                endIdx = stream.find(b"]", lmyIdx + 9)
                if endIdx != -1:
                    msg = stream[lmyIdx + 9 : endIdx].decode("utf-8", errors="replace")
                    scanlines = max(1, min(height, math.ceil(((endIdx + 1) * 4) / max(1, width * 3))))
                    return {
                        "found": True,
                        "binaryFound": True,
                        "message": msg,
                        "rawFrame": f"[LUMIYA::{msg}]",
                        "method": "RGB LSB Stream",
                        "bitPlane": "LSB Bit-Planes 0 & 1 (RGB)",
                        "scanlines": scanlines,
                        "bbox": {
                            "x": 0,
                            "y": 0,
                            "w": width,
                            "h": scanlines,
                        },
                    }

            if isinstance(metaText, str) and "[LUMIYA::" in metaText:
                sIdx = metaText.find("[LUMIYA::") + 9
                eIdx = metaText.rfind("]")
                msg = metaText[sIdx:eIdx] if eIdx != -1 else metaText
                return {
                    "found": True,
                    "binaryFound": True,
                    "message": msg,
                    "rawFrame": f"[LUMIYA::{msg}]",
                    "method": "Container Metadata (PNG tEXt / JPEG COM)",
                    "bitPlane": "Container Metadata Header",
                    "scanlines": 0,
                    "bbox": None,
                }
    except Exception as exc:
        return {"found": False, "message": "", "error": str(exc), "method": "Error"}
    return {"found": False, "message": "", "method": "None"}
