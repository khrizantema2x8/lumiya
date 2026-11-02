import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "mistv2",
    "name": "Mist v2 / AdvDM",
    "attribution": "Liang et al., ICML 2023 (Directed Gradient Error Texture Collapse)",
    "shortInfo": "Injects directed gradient errors into latent representations so unauthorized fine-tuning collapses into chaotic textures.",
    "paperUrl": "https://arxiv.org/abs/2302.04578",
    "hardware": {"tier": "T2", "minVramGb": 16, "requiresCuda": True, "paperHardware": "Not reported; estimate for the full semantic loss"},
}


def transformInput(xDef, step, ctx):
    return xDef


def computeLoss(dist, ctx):
    zMean = dist.mean.float()
    promptBias = float(ctx.get("promptBias", 1.0))
    gradDx = zMean[:, :, :, 1:] - zMean[:, :, :, :-1]
    gradDy = zMean[:, :, 1:, :] - zMean[:, :, :-1, :]
    chaosTerm = -0.22 * (torch.mean(torch.abs(gradDx)) + torch.mean(torch.abs(gradDy)))
    return promptBias * F.mse_loss(zMean, ctx["zTargetMean"]) + chaosTerm

