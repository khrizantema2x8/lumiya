import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "idprotector",
    "name": "IDProtector",
    "attribution": "Multi-Encoder Biometric Identity Inconsistency Defense",
    "shortInfo": "Maximizes facial & biometric identity inconsistency across structural feature scales to prevent unauthorized face cloning.",
    "paperUrl": "https://arxiv.org/search/?query=IDProtector+facial+identity+adversarial+diffusion&searchtype=all",
    "hardware": {"tier": "T3", "minVramGb": 48, "requiresCuda": True, "paperHardware": "RTX A6000 48 GB"},
}


def transformInput(xDef, step, ctx):
    return xDef


def computeLoss(dist, ctx):
    zMean = dist.mean.float()
    zOrig = ctx["zOrigMean"]
    s2 = F.avg_pool2d(zMean, 2, 2)
    s2Orig = F.avg_pool2d(zOrig, 2, 2)
    cos1 = F.cosine_similarity(zMean.flatten(1), zOrig.flatten(1), dim=1).mean()
    cos2 = F.cosine_similarity(s2.flatten(1), s2Orig.flatten(1), dim=1).mean()
    return F.mse_loss(zMean, ctx["zTargetMean"]) + 0.45 * (cos1 + cos2)

