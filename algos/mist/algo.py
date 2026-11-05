import math
import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "mist",
    "name": "Mist",
    "attribution": "Liang et al., SJTU & Chapman Univ., ICML 2023",
    "shortInfo": "Fused textural + semantic attack (Mist / AdvDM): drives VAE latents toward a high-contrast periodic target pattern while maximizing clean latent divergence.",
    "paperUrl": "https://arxiv.org/abs/2305.12683",
    "repoUrl": "https://github.com/mist-project/mist",
    "algoClass": "A",
    "tier": "T1",
    "photoCompatible": True,
    "weightReady": True,
    "hardware": {
        "tier": "T1",
        "minVramGb": 5,
        "requiresCuda": False,
        "paperHardware": "1x NVIDIA RTX 3090 (~6 GB VRAM in fused textural mode)",
    },
    "paper": {"budget": 8.0, "steps": 100},
    "params": ["budget", "compute", "seed"],
}


def _mistPatternTarget(zLike: torch.Tensor, zRef: torch.Tensor) -> torch.Tensor:
    """Synthesizes the tight per-cell high-frequency periodic checkerboard target from mist-project/mist (MIST.png equivalent)."""
    _, c, h, w = zLike.shape
    yy = torch.arange(h, device=zLike.device, dtype=torch.float32).view(1, 1, h, 1)
    xx = torch.arange(w, device=zLike.device, dtype=torch.float32).view(1, 1, 1, w)
    checker = (((yy + xx) % 2) * 2.0 - 1.0)
    chSign = torch.tensor([1.0, -1.0, 1.0, -1.0], device=zLike.device, dtype=torch.float32)[:c].view(1, c, 1, 1)
    dcMean = zRef.detach().mean(dim=(-2, -1), keepdim=True)
    return dcMean + chSign * checker * 1.45


def computeLoss(dist, ctx):
    zAdv = dist.mean.float()
    zOrig = ctx.get("zOrigMean", ctx["zTargetMean"])
    zMist = _mistPatternTarget(zAdv, zOrig)
    # Fused Mist objective: minimize distance to tight high-frequency target while maximizing semantic distance from zOrig
    texturalLoss = F.mse_loss(zAdv, zMist)
    semanticLoss = -F.l1_loss(zAdv, zOrig)
    return texturalLoss + 0.35 * semanticLoss

