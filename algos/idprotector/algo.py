import torch.nn.functional as F

ALGO_META = {
    "id": "idprotector",
    "name": "\u25b2 IDProtector",
    "attribution": "Song et al., ShowLab NUS, CVPR 2025",
    "shortInfo": "Single-pass ViT encoder facial identity protection against tuning-free customization (requires ShowLab pretrained ViT encoder weights).",
    "paperUrl": "https://arxiv.org/abs/2412.11638",
    "repoUrl": "https://github.com/showlab/IDProtector",
    "algoClass": "C",
    "tier": "T1",
    "photoCompatible": True,
    "weightReady": False,
    "blockerReason": "Requires ShowLab pretrained ViT immunizer checkpoint weights (github.com/showlab/IDProtector); use IDGuardian for zero-checkpoint PGD identity cloaking.",
    "hardware": {
        "tier": "T1",
        "minVramGb": 6,
        "requiresCuda": True,
        "paperHardware": "Pretrained ViT encoder inference (6 GB VRAM)",
    },
    "paper": {"budget": 9.0, "steps": 100},
    "params": ["budget", "compute", "seed"],
}


def computeLoss(dist, ctx):
    zAdv = dist.mean.float()
    zOrig = ctx.get("zOrigMean", ctx["zTargetMean"])
    return F.cosine_similarity(zAdv.flatten(1), zOrig.flatten(1), dim=-1).mean() + 0.5 * F.mse_loss(zAdv, ctx["zTargetMean"])
