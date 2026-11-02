import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "chronolock",
    "name": "ChronoLock",
    "attribution": "Temporal Denoising & Cross-Chunk Boundary Disruption",
    "shortInfo": "Secures visual assets against text-to-video personalization by combining intra-chunk chaos and cross-chunk boundary disruption.",
    "paperUrl": "https://arxiv.org/search/?query=temporal+chunk+boundary+adversarial+video+diffusion&searchtype=all",
    "hardware": {"tier": "T3", "minVramGb": 48, "requiresCuda": True, "paperHardware": "Four RTX A6000"},
}


def transformInput(xDef, step, ctx):
    return xDef


def computeLoss(dist, ctx):
    zMean = dist.mean.float()
    tempWeight = float(ctx.get("temporalWeight", 0.5))
    hHalf = max(1, zMean.shape[2] // 2)
    boundaryDelta = F.mse_loss(zMean[:, :, :hHalf, :], zMean[:, :, -hHalf:, :])
    return F.mse_loss(zMean, ctx["zTargetMean"]) - (0.35 * tempWeight) * boundaryDelta

