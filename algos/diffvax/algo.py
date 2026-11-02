import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "diffvax",
    "name": "DiffVax",
    "attribution": "Nested Multi-Scale Spatial & Temporal Cloak Framework",
    "shortInfo": "Uses nested multi-scale skip-connection pooling to disrupt spatial edits and video manipulation.",
    "paperUrl": "https://arxiv.org/search/?query=DiffVax+adversarial+image+protection&searchtype=all",
    "hardware": {"tier": "T1", "minVramGb": 6, "requiresCuda": True, "paperHardware": "5.6 GB inference; training on A100"},
}


def transformInput(xDef, step, ctx):
    p2 = F.avg_pool2d(xDef, kernel_size=2, stride=2)
    u2 = F.interpolate(p2, size=xDef.shape[-2:], mode="bilinear", align_corners=False)
    return 0.80 * xDef + 0.20 * (xDef - u2)


def computeLoss(dist, ctx):
    zMean = dist.mean.float()
    return F.mse_loss(zMean, ctx["zTargetMean"]) - 0.28 * F.mse_loss(zMean, ctx["zOrigMean"])

