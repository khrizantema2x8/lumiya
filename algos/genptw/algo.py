import torch.nn.functional as F

ALGO_META = {
    "id": "genptw",
    "name": "\u25b2 GenPTW",
    "attribution": "Gan et al., AAAI 2026",
    "shortInfo": "Generative Provenance & Tamper-Aware Watermarking in latent diffusion space (requires pretrained watermark encoder/extractor weights).",
    "paperUrl": "https://arxiv.org/abs/2504.19567",
    "repoUrl": "",
    "algoClass": "F",
    "tier": "T1",
    "photoCompatible": True,
    "weightReady": False,
    "blockerReason": "Class F provenance watermark (does not block AI editing); authors have not released the pretrained latent watermark embedder and tamper localization extractor.",
    "hardware": {
        "tier": "T1",
        "minVramGb": 4,
        "requiresCuda": True,
        "paperHardware": "4 GB VRAM with pretrained GenPTW encoder/extractor",
    },
    "paper": {"budget": 8.0, "steps": 50},
    "params": ["budget", "compute", "seed"],
}


def computeLoss(dist, ctx):
    return F.mse_loss(dist.mean.float(), ctx["zTargetMean"])

