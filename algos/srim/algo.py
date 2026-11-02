import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "srim",
    "name": "SRIM",
    "attribution": "Minimax Scale-Robust Optimization Over Geometric Anchors",
    "shortInfo": "Achieves worst-case scale-robust protection via minimax optimization over geometric resizing anchors (1.7 to 7.1).",
    "paperUrl": "https://arxiv.org/search/?query=scale+robust+image+protection+diffusion&searchtype=all",
    "hardware": {"tier": "T3", "minVramGb": 48, "requiresCuda": True, "paperHardware": "L40S 48 GB"},
}


def transformInput(xDef, step, ctx):
    _, _, h, w = xDef.shape
    lowA = float(ctx.get("geoAnchorLow", 1.7))
    highA = float(ctx.get("geoAnchorHigh", 7.1))
    alpha = (step % 4) / 3.0
    anchor = lowA + alpha * max(0.1, highA - lowA)
    ratio = max(0.25, min(0.95, 1.7 / max(anchor, 1.0)))
    sh = max(8, int(round((h * ratio) / 8.0)) * 8)
    sw = max(8, int(round((w * ratio) / 8.0)) * 8)
    xScaled = F.interpolate(xDef, size=(sh, sw), mode="bicubic", align_corners=False)
    return F.interpolate(xScaled, size=(h, w), mode="bicubic", align_corners=False)


def computeLoss(dist, ctx):
    zMean = dist.mean.float()
    diff = (zMean - ctx["zTargetMean"]) ** 2
    worstK = torch.topk(diff.flatten(), k=max(1, diff.numel() // 4)).values.mean()
    return 0.65 * F.mse_loss(zMean, ctx["zTargetMean"]) + 0.35 * worstK

