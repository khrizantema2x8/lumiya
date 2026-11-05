import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "mirage",
    "name": "\u25b2 MIRAGE",
    "attribution": "Nasery et al., Jun 2026",
    "shortInfo": "Multi-model global + top-k worst-crop embedding diversion across vision encoders and safety moderators (5,000 steps; requires 8-model ensemble).",
    "paperUrl": "https://arxiv.org/abs/2606.26199",
    "repoUrl": "",
    "algoClass": "A",
    "tier": "T3",
    "photoCompatible": True,
    "weightReady": False,
    "blockerReason": "No public repository; requires an 8-model CLIP/SigLIP/DINOv2/moderator surrogate ensemble and 5,000 PGD steps.",
    "hardware": {
        "tier": "T3",
        "minVramGb": 16,
        "requiresCuda": True,
        "paperHardware": "1x NVIDIA A100 (16-24 GB VRAM for 8-model vision ensemble + 5,000 steps)",
    },
    "paper": {"budget": 16.0, "steps": 5000},
    "params": ["budget", "compute", "seed"],
}


def computeLoss(dist, ctx):
    zAdv = dist.mean.float()
    zOrig = ctx.get("zOrigMean", ctx["zTargetMean"])
    # Global + 2x2 quadrant top-k worst-crop divergence objective
    globalCos = F.cosine_similarity(zAdv.flatten(1), zOrig.flatten(1), dim=-1).mean()
    _, _, h, w = zAdv.shape
    mh, mw = max(1, h // 2), max(1, w // 2)
    cropsAdv = [zAdv[:, :, :mh, :mw], zAdv[:, :, :mh, mw:], zAdv[:, :, mh:, :mw], zAdv[:, :, mh:, mw:]]
    cropsOrig = [zOrig[:, :, :mh, :mw], zOrig[:, :, :mh, mw:], zOrig[:, :, mh:, :mw], zOrig[:, :, mh:, mw:]]
    cropSims = torch.stack([F.cosine_similarity(ca.flatten(1), co.flatten(1), dim=-1).mean() for ca, co in zip(cropsAdv, cropsOrig)])
    topKSim = torch.topk(cropSims, k=2).values.mean()
    return globalCos + topKSim + 0.35 * F.mse_loss(zAdv, ctx["zTargetMean"])
