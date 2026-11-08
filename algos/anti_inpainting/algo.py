import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "anti_inpainting",
    "name": "Anti-Inpainting",
    "attribution": "Guo et al., Aug 2025",
    "shortInfo": "Selection-based latent resampling with morphological mask dilation/erosion that pushes masked latents outside the benign distribution sphere.",
    "paperUrl": "https://arxiv.org/abs/2505.13023",
    "repoUrl": "",
    "algoClass": "B",
    "tier": "T2",
    "photoCompatible": True,
    "weightReady": True,
    "hardware": {
        "tier": "T2",
        "minVramGb": 8,
        "requiresCuda": True,
        "paperHardware": "1x NVIDIA RTX 4090 (8 GB VRAM)",
    },
    "paper": {"budget": 8.0, "steps": 200, "maskAugFactor": 1.2},
    "params": ["budget", "compute", "seed", "mask", "maskAugFactor"],
}


def transformInput(xDef, step, ctx):
    """Morphological dilation (n > 0) and erosion (n < 0) mask augmentation from arXiv:2505.13023."""
    _, _, h, w = xDef.shape
    baseMask = torch.zeros((1, 1, h, w), device=xDef.device, dtype=xDef.dtype)
    h0, h1 = int(h * 0.2), int(h * 0.8)
    w0, w1 = int(w * 0.2), int(w * 0.8)
    baseMask[:, :, h0:h1, w0:w1] = 1.0

    gamma = max(1, round(3 * float(ctx.get("maskAugFactor", 1.0))))
    offset = (step % (2 * gamma + 1)) - gamma
    kSize = 2 * abs(offset) + 1
    if offset > 0:
        augMask = F.max_pool2d(baseMask, kernel_size=kSize, stride=1, padding=abs(offset))
    elif offset < 0:
        augMask = 1.0 - F.max_pool2d(1.0 - baseMask, kernel_size=kSize, stride=1, padding=abs(offset))
    else:
        augMask = baseMask
    xOrig = ctx.get("xOrigWork", torch.zeros_like(xDef))
    return xDef * (1.0 - augMask) + (0.45 * xDef + 0.55 * xOrig) * augMask


def computeLoss(dist, ctx):
    """Selection-based latent resampling objective: drives latent outside radius tau * r from benign centroid."""
    zMean = dist.mean.float()
    zStd = dist.std.float().clamp(min=1e-4)
    zOrig = ctx.get("zOrigMean", ctx["zTargetMean"])
    # Sample K=6 latent candidates from posterior N(zMean, zStd^2) and select worst-case closer to centroid
    gen = ctx.get("generator")
    epsK = (
        torch.randn((6, *zMean.shape[1:]), generator=gen, device=zMean.device, dtype=zMean.dtype)
        if gen is not None and zMean.device.type == "cpu"
        else torch.randn((6, *zMean.shape[1:]), device=zMean.device, dtype=zMean.dtype)
    )
    zSamples = zMean + zStd * epsK
    dists = torch.norm((zSamples - zOrig).flatten(1), p=2, dim=1)
    # Margin hinge pushing minimum sample distance beyond tau * r (tau = 1.35)
    benignRadius = torch.norm(zOrig.flatten(1), p=2, dim=1).clamp(min=1.0)
    marginLoss = F.relu(1.35 * benignRadius - dists.min())
    return marginLoss + 0.5 * F.mse_loss(zMean, ctx["zTargetMean"])
