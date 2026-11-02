import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "metacloak",
    "name": "MetaCloak",
    "attribution": "Liu et al., CVPR 2024 (Meta-Learned Transformation-Robust Data Poisoning)",
    "shortInfo": "Uses meta-learning style surrogate transformations to craft poisons that survive JPEG compression and Gaussian blur.",
    "paperUrl": "https://arxiv.org/abs/2311.13127",
    "hardware": {"tier": "T3", "minVramGb": 40, "requiresCuda": True, "paperHardware": "Not reported; estimate for several SD copies"},
}


def transformInput(xDef, step, ctx):
    mode = step % 3
    if mode == 0:
        xBlur = F.conv2d(xDef, ctx["blurKernel3"], padding=1, groups=3)
        q = torch.round(xBlur * 96.0) / 96.0
        return xBlur + (q - xBlur).detach()
    if mode == 1:
        _, _, h, w = xDef.shape
        sh, sw = max(8, int(h * 0.85 // 8) * 8), max(8, int(w * 0.85 // 8) * 8)
        return F.interpolate(F.interpolate(xDef, size=(sh, sw), mode="bilinear", align_corners=False), size=(h, w), mode="bilinear", align_corners=False)
    q = torch.round(xDef * 64.0) / 64.0
    return xDef + (q - xDef).detach()


def computeLoss(dist, ctx):
    zMean = dist.mean.float()
    return F.mse_loss(zMean, ctx["zTargetMean"]) + 0.30 * F.mse_loss(dist.std.float(), ctx["zTargetStd"])

