import torch.nn.functional as F

ALGO_META = {
    "id": "photoguard",
    "name": "PhotoGuard",
    "attribution": "Salman et al., MIT, ICML 2023",
    "shortInfo": "Encoder attack: moves the photo's VAE latent toward a gray target so diffusion editors start from a collapsed representation.",
    "paperUrl": "https://arxiv.org/abs/2302.06588",
    "repoUrl": "https://github.com/MadryLab/photoguard",
    "algoClass": "A",
    "tier": "T1",
    "photoCompatible": True,
    "weightReady": True,
    "hardware": {
        "tier": "T1",
        "minVramGb": 5,
        "requiresCuda": False,
        "paperHardware": "Encoder attack; 5.2 GB measured on a 23 MP photo",
    },
    "paper": {"budget": 8.0, "steps": 200},
    "params": ["budget", "compute", "seed"],
}


def computeLoss(dist, ctx):
    return F.mse_loss(dist.mean.float(), ctx["zTargetMean"])
