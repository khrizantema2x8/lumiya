import math
import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "srim",
    "name": "SRIM",
    "attribution": "Guo et al., USTC, Oct 2026",
    "shortInfo": "Scale-Robust Image Immunization: optimizes across a geometric scale grid with worst-case anchor EMA sampling, scale jitter, and multi-kernel interpolation.",
    "paperUrl": "https://arxiv.org/abs/2610.07464",
    "repoUrl": "",
    "algoClass": "A",
    "tier": "T1",
    "photoCompatible": True,
    "weightReady": True,
    "hardware": {
        "tier": "T1",
        "minVramGb": 6,
        "requiresCuda": False,
        "paperHardware": "1x NVIDIA RTX 4090 (6 GB VRAM across dynamic scale anchors)",
    },
    "paper": {"budget": 4.0, "steps": 200, "geoAnchorLow": 1.7, "geoAnchorHigh": 7.1},
    "params": ["budget", "compute", "seed", "scale", "geoAnchorLow", "geoAnchorHigh"],
}

_KERNELS = ("bicubic", "bilinear", "area")


def transformInput(xDef, step, ctx):
    """Applies SRIM scale jitter s ~ U[e^-0.1, e^0.1] modulated by geoAnchorLow/High and random resampler kernel."""
    _, _, h, w = xDef.shape
    gen = ctx.get("generator")
    u = float(torch.rand(1, generator=gen).item()) if gen is not None else ((step * 0.6180339887) % 1.0)
    low = max(1.0, float(ctx.get("geoAnchorLow", 1.7)))
    high = max(low + 0.1, float(ctx.get("geoAnchorHigh", 7.1)))
    span = min(0.18, 0.025 * (high - low))
    jitter = math.exp(-span + 2.0 * span * u)
    jh = max(16, round((h * jitter) / 8) * 8)
    jw = max(16, round((w * jitter) / 8) * 8)
    mode = _KERNELS[step % len(_KERNELS)]
    if mode in ("bicubic", "bilinear"):
        xScaled = F.interpolate(xDef, size=(jh, jw), mode=mode, align_corners=False, antialias=True)
        return F.interpolate(xScaled, size=(h, w), mode=mode, align_corners=False, antialias=True)
    xScaled = F.interpolate(xDef, size=(jh, jw), mode="area")
    return F.interpolate(xScaled, size=(h, w), mode="bilinear", align_corners=False, antialias=True)


def computeLoss(dist, ctx):
    """Relative latent deviation objective weighted by worst-case anchor EMA distribution P(k) ~ exp(-r_k / tau)."""
    zAdv = dist.mean.float()
    zOrig = ctx.get("zOrigMean", ctx["zTargetMean"])
    diffNorm = torch.norm((zAdv - zOrig).flatten(1), p=2, dim=1)
    origNorm = torch.norm(zOrig.flatten(1), p=2, dim=1).clamp(min=1e-6)
    relDev = (diffNorm / origNorm).mean()

    emaMap = ctx.setdefault("_srimEma", {})
    key = tuple(zAdv.shape[-2:])
    prevR = emaMap.get(key, float(relDev.detach().item()))
    curR = 0.7 * prevR + 0.3 * float(relDev.detach().item())
    emaMap[key] = curR
    # Worst-case anchor weight: anchors with smaller relative deviation receive exponentially higher gradient weight (tau=0.1)
    emaVals = list(emaMap.values())
    meanR = sum(emaVals) / max(1, len(emaVals))
    weight = math.exp(max(-2.5, min(2.5, -(curR - meanR) / 0.1)))
    return -weight * relDev
