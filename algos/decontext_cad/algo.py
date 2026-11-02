import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "decontext_cad",
    "name": "DeContext & CaD",
    "attribution": "Early-Timestep DiT Context Detachment Defense",
    "shortInfo": "Restricts optimization to early timesteps and context-heavy blocks in Diffusion Transformers to detach input-output links.",
    "paperUrl": "https://arxiv.org/search/?query=DeContext+Diffusion+Transformer+defense&searchtype=all",
    "hardware": {"tier": "T3", "minVramGb": 80, "requiresCuda": True, "paperHardware": "A800 80 GB"},
}


def transformInput(xDef, step, ctx):
    return xDef


def computeLoss(dist, ctx):
    zMean = dist.mean.float()
    zOrig = ctx["zOrigMean"]
    patchMean = F.avg_pool2d(zMean, kernel_size=4, stride=4)
    origPatch = F.avg_pool2d(zOrig, kernel_size=4, stride=4)
    return F.mse_loss(zMean, ctx["zTargetMean"]) - 0.45 * F.mse_loss(patchMean, origPatch)

