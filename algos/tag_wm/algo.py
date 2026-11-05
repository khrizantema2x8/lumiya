import torch.nn.functional as F

ALGO_META = {
    "id": "tag_wm",
    "name": "\u25b2 TAG-WM (In-Gen Only)",
    "attribution": "Chen et al., Jun 2025",
    "shortInfo": "Tamper-Aware Generative Watermarking injected into initial Gaussian noise prior to DDIM text-to-image sampling (cannot watermark existing user photos).",
    "paperUrl": "https://arxiv.org/abs/2506.23484",
    "repoUrl": "https://github.com/Suchenl/TAG-WM",
    "algoClass": "F",
    "tier": "T2",
    "photoCompatible": False,
    "weightReady": False,
    "blockerReason": "TAG-WM operates strictly in-generation by seeding initial Gaussian noise before DDIM text-to-image sampling; it cannot protect or watermark an uploaded photograph.",
    "hardware": {
        "tier": "T2",
        "minVramGb": 8,
        "requiresCuda": True,
        "paperHardware": "In-generation DDIM sampling hook (8 GB VRAM)",
    },
    "paper": {"budget": 8.0, "steps": 50},
    "params": ["budget", "compute", "seed"],
}


def computeLoss(dist, ctx):
    return F.mse_loss(dist.mean.float(), ctx["zTargetMean"])

