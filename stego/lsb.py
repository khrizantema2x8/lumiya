"""Steganography service: embeds and reads the Lumiya LSB frame. Independent of the algo plugins."""
from __future__ import annotations

import io
from typing import Any, Dict

import numpy as np

try:
    from PIL import Image
except ImportError:
    Image = None


def applySteganographyPil(pilImg: Any, secretMessage: str) -> Any:
    """Embeds a cyclic 2-bit LSB UTF-8 frame across RGB channels for reliable stego checker detection."""
    rgbImg = pilImg.convert("RGB")
    msgBytes = secretMessage.encode("utf-8")[:32767]
    bodyBytes = f"[LUMIYA::{secretMessage}]".encode("utf-8")
    frameBytes = b"LMY1" + len(msgBytes).to_bytes(2, "big") + msgBytes + b"::" + bodyBytes
    pairs = [(byteVal >> shift) & 3 for byteVal in frameBytes for shift in (6, 4, 2, 0)]
    if not pairs:
        return rgbImg

    totalPairs = len(pairs)
    arr = np.array(rgbImg, dtype=np.uint8)
    h, w, c = arr.shape
    flat = arr.reshape(-1)
    idx = np.arange(flat.size)
    pairsArr = np.array(pairs, dtype=np.uint8)
    flat = (flat & 0xFC) | pairsArr[idx % totalPairs]
    return Image.fromarray(flat.reshape(h, w, c))


def extractSteganographyPil(rawBytes: bytes) -> Dict[str, Any]:
    """Extracts and verifies embedded Lumiya steganographic payload from image pixels or container metadata."""
    if Image is None or not rawBytes:
        return {"found": False, "message": "", "method": "Unavailable"}
    try:
        with Image.open(io.BytesIO(rawBytes)) as im:
            metaText = im.info.get("LumiyaStego") or im.info.get("comment")
            if isinstance(metaText, bytes):
                metaText = metaText.decode("utf-8", errors="replace")
            if isinstance(metaText, str) and "[LUMIYA::" in metaText:
                sIdx = metaText.find("[LUMIYA::") + 9
                eIdx = metaText.rfind("]")
                msg = metaText[sIdx:eIdx] if eIdx != -1 else metaText
                return {
                    "found": True,
                    "message": msg,
                    "rawFrame": f"[LUMIYA::{msg}]",
                    "method": "Container Metadata",
                }
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
                    return {
                        "found": True,
                        "message": msg,
                        "rawFrame": f"[LUMIYA::{msg}]",
                        "method": "2-Bit RGB LSB + Cyclic Frame",
                    }

            lmyIdx = stream.find(b"[LUMIYA::")
            if lmyIdx != -1:
                endIdx = stream.find(b"]", lmyIdx + 9)
                if endIdx != -1:
                    msg = stream[lmyIdx + 9 : endIdx].decode("utf-8", errors="replace")
                    return {
                        "found": True,
                        "message": msg,
                        "rawFrame": f"[LUMIYA::{msg}]",
                        "method": "RGB LSB Stream",
                    }
    except Exception as exc:
        return {"found": False, "message": "", "error": str(exc), "method": "Error"}
    return {"found": False, "message": "", "method": "None"}
