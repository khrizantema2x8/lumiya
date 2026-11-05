import torch.nn.functional as F

ALGO_META = {
    "id": "diffvax",
    "name": "\u25b2 DiffVax",
    "attribution": "Ozden et al., ICLR 2026",
    "shortInfo": "Optimization-free single-forward-pass image immunization via a trained UNet++ generator network (requires pretrained UNet++ checkpoint).",
    "paperUrl": "https://arxiv.org/abs/2411.17957",
    "repoUrl": "https://DiffVax.github.io",
    "algoClass": "C",
    "tier": "T0",
    "photoCompatible": True,
    "weightReady": False,
    "blockerReason": "Requires the authors' pretrained UNet++ immunizer checkpoint (22 GPU-hours on A100 per target editor); weights not yet published on DiffVax.github.io.",
    "hardware": {
        "tier": "T0",
        "minVramGb": 2,
        "requiresCuda": False,
        "paperHardware": "22h A100 training; <2 GB VRAM at inference once UNet++ weights are loaded",
    },
    "paper": {"budget": 16.0, "steps": 50},
    "params": ["budget", "compute", "seed"],
}


def computeLoss(dist, ctx):
    return F.mse_loss(dist.mean.float(), ctx["zTargetMean"])
