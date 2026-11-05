import torch.nn.functional as F

ALGO_META = {
    "id": "tc_uap",
    "name": "\u25b2 TC-UAP",
    "attribution": "Huang et al., NeurIPS 2026",
    "shortInfo": "Temporally Consistent Universal Adversarial Perturbation against 3D video VAEs and video portrait customization.",
    "paperUrl": "https://arxiv.org/abs/2607.13336",
    "repoUrl": "",
    "algoClass": "E",
    "tier": "T2",
    "photoCompatible": True,
    "weightReady": False,
    "blockerReason": "No public repository or complete hyper-parameter specification (window length, loss weights, and 3D video VAE UAP bank not released).",
    "hardware": {
        "tier": "T2",
        "minVramGb": 8,
        "requiresCuda": True,
        "paperHardware": "Multi-frame 3D Video VAE UAP optimization (8-16 GB VRAM)",
    },
    "paper": {"budget": 8.0, "steps": 100},
    "params": ["budget", "compute", "seed", "temporalWeight"],
}


def computeLoss(dist, ctx):
    return F.mse_loss(dist.mean.float(), ctx["zTargetMean"])

