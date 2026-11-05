import torch.nn.functional as F

ALGO_META = {
    "id": "fastprotect",
    "name": "\u25b2 FastProtect",
    "attribution": "Ahn et al., NAVER WEBTOON AI, CVPR 2025",
    "shortInfo": "Real-time adaptive mixture of K=4 pre-computed K-means++ cluster perturbations and 3 target pattern banks (requires pretrained cluster tensors).",
    "paperUrl": "https://arxiv.org/abs/2412.11423",
    "repoUrl": "https://webtoon.github.io/impasto",
    "algoClass": "C",
    "tier": "T0",
    "photoCompatible": True,
    "weightReady": False,
    "blockerReason": "Requires NAVER WEBTOON's pre-computed K=4 K-means++ cluster centroids and 3 target pattern perturbation banks (unreleased).",
    "hardware": {
        "tier": "T0",
        "minVramGb": 2,
        "requiresCuda": False,
        "paperHardware": "2 GB VRAM at inference using pre-computed cluster perturbation banks",
    },
    "paper": {"budget": 8.0, "steps": 50},
    "params": ["budget", "compute", "seed"],
}


def computeLoss(dist, ctx):
    return F.mse_loss(dist.mean.float(), ctx["zTargetMean"])

