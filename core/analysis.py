"""Forensic Analytics: the heavier Inspect tools that run on the server, each on real file bytes or a real model."""
from __future__ import annotations

import base64
import io
import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from stego.mark import inspectStego

ANALYSIS_LOCK = threading.Lock()
LATENT_MAX_SIDE = 768


def _rgb(raw: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(raw))
    img.load()
    return ImageOps.exif_transpose(img).convert("RGB")


def _heatPng(field: np.ndarray, scaleMax: float) -> str:
    """One fixed ramp, black -> red -> yellow -> white, from 0 to scaleMax (stated in the result)."""
    t = np.clip(field / max(scaleMax, 1e-12), 0.0, 1.0)
    r = np.clip(t * 3.0, 0, 1)
    g = np.clip(t * 3.0 - 1.0, 0, 1)
    b = np.clip(t * 3.0 - 2.0, 0, 1)
    rgb = (np.stack([r, g, b], axis=-1) * 255.0 + 0.5).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def trueEla(after: bytes, quality: int = 90) -> Dict[str, Any]:
    """Real error level analysis: re-save as JPEG at `quality`, decode, and take the per-pixel difference."""
    quality = max(1, min(100, int(quality)))
    img = _rgb(after)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    resaved = np.asarray(_rgb(buf.getvalue()), dtype=np.float32)
    diff = np.abs(np.asarray(img, dtype=np.float32) - resaved).max(axis=-1)
    p99 = float(np.percentile(diff, 99))
    return {
        "png": _heatPng(diff, p99),
        "scale": f"0 to {p99:.1f} levels (99th percentile)",
        "stats": {"Mean error": f"{diff.mean():.2f}", "99th pct": f"{p99:.1f}", "Max": f"{diff.max():.0f}", "JPEG quality": str(quality)},
        "method": f"PIL JPEG re-save at Q{quality}, max abs channel difference",
    }


def _jpeg(img: Image.Image, q: int) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=q)
    return buf.getvalue()


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def robustness(after: bytes) -> Dict[str, Any]:
    """Applies everyday edits to the photo and re-runs the real mark decoder on each copy."""
    img = _rgb(after)
    w, h = img.size
    cw, ch = int(w * 0.1), int(h * 0.1)
    attacks: Dict[str, Callable[[], bytes]] = {
        "Original file": lambda: after,
        "JPEG Q90": lambda: _jpeg(img, 90),
        "JPEG Q75": lambda: _jpeg(img, 75),
        "JPEG Q50": lambda: _jpeg(img, 50),
        "Resize 50% and back": lambda: _png(img.resize((max(1, w // 2), max(1, h // 2)), Image.LANCZOS).resize((w, h), Image.LANCZOS)),
        "Crop 10% each side": lambda: _png(img.crop((cw, ch, w - cw, h - ch))),
        "Gaussian blur r=1": lambda: _png(img.filter(ImageFilter.GaussianBlur(1))),
    }
    rows = []
    for name, make in attacks.items():
        res = inspectStego(make(), foreign=False)
        rows.append({
            "attack": name,
            "markFound": bool(res.get("markFound")),
            "markScore": res.get("markScore"),
            "lsbFound": bool(res.get("binaryFound")),
        })
    return {"rows": rows, "method": "Each copy is decoded by stego.mark.inspectStego, the same reader as the Scanner panel"}


def _toLatentInput(img: Image.Image, torch: Any, device: str, dtype: Any) -> Any:
    w, h = img.size
    s = min(1.0, LATENT_MAX_SIDE / float(max(w, h)))
    nw, nh = max(8, int(w * s) // 8 * 8), max(8, int(h * s) // 8 * 8)
    arr = np.asarray(img.resize((nw, nh), Image.LANCZOS), dtype=np.float32) / 127.5 - 1.0
    return torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).to(device=device, dtype=dtype)


def _latentShiftCompute(vae: Any, device: str, dtype: Any, before: bytes, after: bytes) -> Dict[str, Any]:
    import torch

    a, b = _rgb(before), _rgb(after)
    if a.size != b.size:
        b = b.resize(a.size, Image.LANCZOS)
    with torch.no_grad():
        za = vae.encode(_toLatentInput(a, torch, device, dtype)).latent_dist.mean.float()
        zb = vae.encode(_toLatentInput(b, torch, device, dtype)).latent_dist.mean.float()
    shift = (zb - za).pow(2).sum(dim=1).sqrt()[0].cpu().numpy()
    baseNorm = float(za.pow(2).sum(dim=1).sqrt().mean())
    cos = float(torch.nn.functional.cosine_similarity(za.flatten(), zb.flatten(), dim=0))
    p99 = float(np.percentile(shift, 99))
    return {
        "png": _heatPng(shift, p99),
        "scale": f"0 to {p99:.3f} latent L2 (99th percentile)",
        "stats": {
            "Mean shift": f"{shift.mean():.4f}",
            "Relative to latent norm": f"{100.0 * shift.mean() / max(baseNorm, 1e-9):.2f}%",
            "Cosine similarity": f"{cos:.5f}",
            "Latent grid": f"{shift.shape[1]}x{shift.shape[0]}",
        },
        "method": f"stabilityai/sd-vae-ft-mse encoder mean on {device.upper()}, images scaled to max {LATENT_MAX_SIDE}px",
    }


def _latentShiftSubprocess(before: bytes, after: bytes, device: str, precision: str) -> Dict[str, Any]:
    """Runs PyTorch/VAE encoding in a short-lived child process so the web server never imports torch."""
    rootDir = Path(__file__).resolve().parents[1]
    startupInfo = None
    if sys.platform == "win32":
        startupInfo = subprocess.STARTUPINFO()
        startupInfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    with tempfile.TemporaryDirectory(prefix="lumiya_latent_") as td:
        beforePath = Path(td) / "before.bin"
        afterPath = Path(td) / "after.bin"
        beforePath.write_bytes(before)
        afterPath.write_bytes(after)
        proc = subprocess.run(
            [sys.executable, "-m", "core.analysis", str(beforePath), str(afterPath), device, precision],
            cwd=str(rootDir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180.0,
            startupinfo=startupInfo,
        )
    if proc.returncode != 0:
        errLine = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise RuntimeError(errLine[-1] if errLine else f"Latent Shift worker failed (exit {proc.returncode})")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def latentShift(engine: Any, before: bytes, after: bytes, precision: str = "fp16") -> Dict[str, Any]:
    """Encodes both images with the real SD VAE and maps how far each latent cell moved (L2 over the 4 channels)."""
    if getattr(engine, "useSubprocess", False):
        if not getattr(engine, "majorDepsReady", True):
            raise RuntimeError("Missing required dependencies. Open Configuration tab to install.")
        device = engine.resolveDevice() if hasattr(engine, "resolveDevice") else "auto"
        return _latentShiftSubprocess(before, after, device, precision)

    import gc
    import torch

    try:
        device, dtype = engine.ensureLoaded()
        return _latentShiftCompute(engine.vae, device, dtype, before, after)
    finally:
        if hasattr(engine, "unloadModel"):
            engine.unloadModel()
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def runAnalysis(tool: str, engine: Any, before: Optional[bytes], after: bytes, params: Dict[str, Any]) -> Dict[str, Any]:
    if not ANALYSIS_LOCK.acquire(blocking=False):
        return {"ok": False, "error": "Another analysis is still running."}
    try:
        t0 = time.time()
        if tool == "ela":
            res = trueEla(after, int(params.get("quality", 90)))
        elif tool == "robust":
            res = robustness(after)
        elif tool == "latent":
            if not before:
                return {"ok": False, "error": "Latent Shift needs the original photo, and it is not available for this item."}
            res = latentShift(engine, before, after, precision=str(params.get("precision", "fp16")))
        else:
            return {"ok": False, "error": f"Unknown tool: {tool}"}
        res.update({"ok": True, "tool": tool, "seconds": round(time.time() - t0, 2)})
        return res
    except Exception as exc:  # report, never crash the request thread
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        ANALYSIS_LOCK.release()


if __name__ == "__main__":
    import warnings
    import torch
    from diffusers import AutoencoderKL

    _beforePath, _afterPath, _reqDev, _reqPrec = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    _device = "cuda" if (_reqDev in ("auto", "cuda") and torch.cuda.is_available()) else "cpu"
    _dtype = torch.float16 if (_device == "cuda" and _reqPrec == "fp16") else torch.float32
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            _vae = AutoencoderKL.from_pretrained("stabilityai/sd-vae-ft-mse", torch_dtype=_dtype, local_files_only=True).to(_device)
        except Exception:
            _vae = AutoencoderKL.from_pretrained("stabilityai/sd-vae-ft-mse", torch_dtype=_dtype).to(_device)
    _vae.eval()
    print(json.dumps(_latentShiftCompute(_vae, _device, _dtype, Path(_beforePath).read_bytes(), Path(_afterPath).read_bytes())))
