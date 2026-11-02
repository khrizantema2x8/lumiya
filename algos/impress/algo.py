import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "impress",
    "name": "IMPRESS",
    "attribution": "Cao et al., NeurIPS 2023 (High-Frequency Perturbation Concentration & Purification Defense)",
    "shortInfo": "Concentrates perturbation power into structural high-frequency bands that low-pass purifiers fail to strip.",
    "paperUrl": "https://arxiv.org/abs/2310.19248",
    "hardware": {"tier": "T2", "minVramGb": 8, "requiresCuda": True, "paperHardware": "Not reported; estimate"},
}


def transformInput(xDef, step, ctx):
    xLow = F.conv2d(xDef, ctx["blurKernel3"], padding=1, groups=3)
    xHigh = xDef - xLow
    return torch.clamp(xDef + 0.35 * xHigh, -1.0, 1.0)


def computeLoss(dist, ctx):
    zMean = dist.mean.float()
    zCenter = F.avg_pool2d(zMean, kernel_size=3, stride=1, padding=1)
    hfEnergy = torch.mean((zMean - zCenter) ** 2)
    return F.mse_loss(zMean, ctx["zTargetMean"]) - 0.25 * hfEnergy

