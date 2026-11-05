import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "metacloak",
    "name": "MetaCloak",
    "attribution": "Liu et al., Lehigh Univ., CVPR 2024",
    "shortInfo": "Transformation-robust meta-learning immunization with Expectation Over Transformation (EOT: crop, Gaussian blur, differentiable quantization STE).",
    "paperUrl": "https://arxiv.org/abs/2311.13127",
    "repoUrl": "https://github.com/liuyixin-louis/MetaCloak",
    "algoClass": "D",
    "tier": "T3",
    "photoCompatible": True,
    "weightReady": True,
    "hardware": {
        "tier": "T3",
        "minVramGb": 12,
        "requiresCuda": True,
        "paperHardware": "1x NVIDIA A100 (12-24 GB VRAM for staggered surrogate pool + EOT)",
    },
    "paper": {"budget": 11.0, "steps": 120},
    "params": ["budget", "compute", "seed"],
}


def transformInput(xDef, step, ctx):
    """Applies MetaCloak's EOT transformation pool (Gaussian blur + random spatial shift + Straight-Through Estimator quantization)."""
    mode = step % 3
    if mode == 0:
        # Differentiable 5x5 Gaussian blur
        coords = torch.tensor([-2.0, -1.0, 0.0, 1.0, 2.0], device=xDef.device, dtype=xDef.dtype)
        g1 = torch.exp(-(coords ** 2) / (2.0 * (1.15 ** 2)))
        g1 = g1 / g1.sum()
        k2 = torch.outer(g1, g1).view(1, 1, 5, 5).repeat(xDef.shape[1], 1, 1, 1)
        xTrans = F.conv2d(F.pad(xDef, (2, 2, 2, 2), mode="reflect"), k2, groups=xDef.shape[1])
    elif mode == 1:
        # Random crop-and-resize EOT
        _, _, h, w = xDef.shape
        ch, cw = max(16, int(h * 0.92)), max(16, int(w * 0.92))
        y0 = (step * 7) % max(1, h - ch)
        x0 = (step * 11) % max(1, w - cw)
        xTrans = F.interpolate(xDef[:, :, y0 : y0 + ch, x0 : x0 + cw], size=(h, w), mode="bilinear", align_corners=False)
    else:
        xTrans = xDef

    # Differentiable quantization Straight-Through Estimator (STE) simulating lossy re-saving
    qLevels = 32.0
    xQuant = torch.round((xTrans + 1.0) * 0.5 * qLevels) / qLevels * 2.0 - 1.0
    return xTrans + (xQuant - xTrans).detach()


def computeLoss(dist, ctx):
    zAdv = dist.mean.float()
    zOrig = ctx.get("zOrigMean", ctx["zTargetMean"])
    # Staggered multi-scale feature divergence + gray collapse
    s1 = F.mse_loss(zAdv, ctx["zTargetMean"])
    s2 = -F.l1_loss(F.avg_pool2d(zAdv, 2), F.avg_pool2d(zOrig, 2))
    return s1 + 0.45 * s2
