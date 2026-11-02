import torch.nn.functional as F

ALGO_META = {
    "id": "diffusionguard",
    "name": "DiffusionGuard",
    "attribution": "Choi et al., ICLR 2025 (Contour-Based Mask Augmentation Inpainting Defense)",
    "shortInfo": "Maximizes U-Net & posterior error using contour-shrink mask augmentation against varied inpainting masks.",
    "paperUrl": "https://arxiv.org/abs/2410.05694",
    "hardware": {"tier": "T2", "minVramGb": 24, "requiresCuda": True, "paperHardware": "H100; estimate"},
}


def transformInput(xDef, step, ctx):
    _, _, h, w = xDef.shape
    maskStrength = float(ctx.get("maskAugFactor", 1.0))
    ratio = max(0.18, min(0.55, 0.30 * maskStrength))
    mh, mw = max(12, int(h * ratio)), max(12, int(w * ratio))
    y0 = (step * 37) % max(1, h - mh)
    x0 = (step * 53) % max(1, w - mw)
    xMasked = xDef.clone()
    xMasked[:, :, y0 : y0 + mh, x0 : x0 + mw] = xDef[:, :, y0 : y0 + mh, x0 : x0 + mw] * 0.15
    return xMasked


def computeLoss(dist, ctx):
    return F.mse_loss(dist.mean.float(), ctx["zTargetMean"]) + 0.35 * F.mse_loss(dist.std.float(), ctx["zTargetStd"])
