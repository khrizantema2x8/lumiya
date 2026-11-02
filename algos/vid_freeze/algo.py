import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "vid_freeze",
    "name": "Vid-Freeze",
    "attribution": "Motion Dynamics Suppression via Target Attention Freezing Loss",
    "shortInfo": "Suppresses motion dynamics via freezing loss so video generators collapse into static frame repetition.",
    "paperUrl": "https://arxiv.org/search/?query=video+diffusion+adversarial+motion+freezing&searchtype=all",
    "hardware": {"tier": "T3", "minVramGb": 60, "requiresCuda": True, "paperHardware": "60 to 80 GB class"},
}


def transformInput(xDef, step, ctx):
    return xDef


def computeLoss(dist, ctx):
    zMean = dist.mean.float()
    tempWeight = float(ctx.get("temporalWeight", 0.5))
    shiftX = torch.roll(zMean, shifts=1, dims=-1)
    shiftY = torch.roll(zMean, shifts=1, dims=-2)
    motionFreeze = (F.mse_loss(zMean, shiftX) + F.mse_loss(zMean, shiftY)) * (0.30 * tempWeight)
    return F.mse_loss(zMean, ctx["zTargetMean"]) + motionFreeze

