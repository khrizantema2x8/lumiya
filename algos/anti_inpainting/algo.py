import torch.nn.functional as F

ALGO_META = {
    "id": "antiInpainting",
    "name": "Anti-Inpainting",
    "attribution": "9-Channel Masked Boundary Context Poisoning (SD-Inpaint / ControlNet)",
    "shortInfo": "Simulates stochastic brush masks during PGD to poison unmasked surrounding context.",
    "paperUrl": "https://arxiv.org/abs/2302.06588",
    "hardware": {"tier": "T2", "minVramGb": 16, "requiresCuda": True, "paperHardware": "RTX 3090, up to 16 GB"},
}


def transformInput(xDef, step, ctx):
    _, _, height, width = xDef.shape
    maskFactor = float(ctx.get("maskAugFactor", 1.0))
    div = max(2, min(5, int(round(3.0 / max(maskFactor, 0.3)))))
    maskH, maskW = max(16, height // div), max(16, width // div)
    y0 = (step * 41) % max(1, height - maskH)
    x0 = (step * 59) % max(1, width - maskW)
    xMasked = xDef.clone()
    xMasked[:, :, y0 : y0 + maskH, x0 : x0 + maskW] = -0.5
    return xMasked


def computeLoss(dist, ctx):
    return F.mse_loss(dist.mean.float(), ctx["zTargetMean"]) + 0.25 * F.mse_loss(dist.std.float(), ctx["zTargetStd"])
