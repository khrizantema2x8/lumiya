import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "antipure",
    "name": "AntiPure",
    "attribution": "Erroneous Timestep Guidance Against Diffusion Purifiers (DiffPure Defense)",
    "shortInfo": "Weaponizes diffusion purification attempts via erroneous timestep guidance so purifiers embed noise deeper.",
    "paperUrl": "https://arxiv.org/search/?query=diffusion+purification+adversarial+defense+DiffPure&searchtype=all",
    "hardware": {"tier": "T2", "minVramGb": 8, "requiresCuda": True, "paperHardware": "Not reported; estimate for a 256 px purifier"},
}


def transformInput(xDef, step, ctx):
    xBlur = F.conv2d(xDef, ctx["blurKernel3"], padding=1, groups=3)
    return 1.25 * xDef - 0.25 * xBlur


def computeLoss(dist, ctx):
    zMean = dist.mean.float()
    zStd = dist.std.float()
    return F.mse_loss(zMean, ctx["zTargetMean"]) + 0.45 * F.mse_loss(zStd, ctx["zTargetStd"]) - 0.15 * torch.mean(zStd)

