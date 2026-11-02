import torch.nn.functional as F

ALGO_META = {
    "id": "photoguard",
    "name": "PhotoGuard",
    "attribution": "Salman et al., MIT, ICML 2023",
    "shortInfo": "Encoder attack: moves the photo's VAE latent toward a gray image so diffusion editors start from a corrupted representation.",
    "paperUrl": "https://arxiv.org/abs/2302.06588",
    "hardware": {"tier": "T1", "minVramGb": 5, "requiresCuda": False, "paperHardware": "Encoder attack; 5.2 GB measured here on a 23 MP photo"},
    "paper": {"budget": 16.0, "steps": 200},
    "params": ["budget", "compute", "seed"],
}


def computeLoss(dist, ctx):
    return F.mse_loss(dist.mean.float(), ctx["zTargetMean"])
