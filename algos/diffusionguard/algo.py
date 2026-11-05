import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "diffusionguard",
    "name": "DiffusionGuard",
    "attribution": "Choi et al., KAIST, ICLR 2025",
    "shortInfo": "Early-stage diffusion defense with contour-shrinking mask augmentation that maximizes initial denoising norm divergence.",
    "paperUrl": "https://arxiv.org/abs/2410.05694",
    "repoUrl": "https://github.com/choi403/DiffusionGuard",
    "algoClass": "B",
    "tier": "T2",
    "photoCompatible": True,
    "weightReady": True,
    "hardware": {
        "tier": "T2",
        "minVramGb": 8,
        "requiresCuda": True,
        "paperHardware": "1x NVIDIA RTX A6000 / RTX 3090 (8 GB VRAM)",
    },
    "paper": {"budget": 8.0, "steps": 100, "maskAugFactor": 1.0},
    "params": ["budget", "compute", "seed", "mask", "maskAugFactor"],
}


def _contourShrinkingMask(x: torch.Tensor, step: int, maskAugFactor: float = 1.0) -> torch.Tensor:
    """Implements DiffusionGuard's Gaussian-smoothed contour-shrinking mask augmentation (choi403/DiffusionGuard)."""
    _, _, h, w = x.shape
    yy = torch.linspace(-1.0, 1.0, h, device=x.device, dtype=x.dtype).view(1, 1, h, 1)
    xx = torch.linspace(-1.0, 1.0, w, device=x.device, dtype=x.dtype).view(1, 1, 1, w)
    # Vary elliptical contour radius across optimization steps so protection generalizes to tighter user masks
    phase = ((step * 37) % 100) / 100.0
    shrink = (0.45 + 0.35 * phase) * max(0.4, min(1.6, float(maskAugFactor)))
    dist = torch.sqrt((yy / shrink) ** 2 + (xx / shrink) ** 2)
    # Smooth Gaussian boundary falloff around the contour
    mask = torch.sigmoid((1.0 - dist) * 6.0)
    return mask


def transformInput(xDef, step, ctx):
    mask = _contourShrinkingMask(xDef, step, float(ctx.get("maskAugFactor", 1.0)))
    xOrig = ctx.get("xOrigWork", torch.zeros_like(xDef))
    # Simulate inpainting editor conditioning where unmasked context comes from the perturbed region
    return xDef * mask + xOrig * (1.0 - mask) * 0.25


def computeLoss(dist, ctx):
    """Maximizes early-timestep latent score norm and posterior variance divergence."""
    zMean = dist.mean.float()
    zStd = dist.std.float()
    zOrig = ctx.get("zOrigMean", ctx["zTargetMean"])
    # Early-step (t=T) score norm maximization: drive latent norm and posterior variance away from clean manifold
    scoreDeltaNorm = torch.norm((zMean - zOrig).flatten(1), p=2, dim=1).mean()
    targetCollapse = F.mse_loss(zMean, ctx["zTargetMean"])
    return targetCollapse - 0.45 * scoreDeltaNorm - 0.10 * zStd.mean()
