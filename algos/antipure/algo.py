import math
import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "antipure",
    "name": "AntiPure",
    "attribution": "Yang et al., ICCV 2025",
    "shortInfo": "Purification-resilient immunization combining Patch-wise Frequency Guidance (2D DCT high-frequency quadrant) and Erroneous Timestep Guidance.",
    "paperUrl": "https://arxiv.org/abs/2509.13922",
    "repoUrl": "",
    "algoClass": "B",
    "tier": "T2",
    "photoCompatible": True,
    "weightReady": True,
    "hardware": {
        "tier": "T2",
        "minVramGb": 8,
        "requiresCuda": True,
        "paperHardware": "1x NVIDIA A100 / RTX 4090 (8 GB VRAM)",
    },
    "paper": {"budget": 8.0, "steps": 100},
    "params": ["budget", "compute", "seed"],
}


def _patchHighFreqEnergy(x: torch.Tensor, patchSize: int = 8) -> torch.Tensor:
    """Computes Patch-wise Frequency Guidance (PFG) on bottom-right high-frequency quadrant of s x s patches."""
    b, c, h, w = x.shape
    hp = (h // patchSize) * patchSize
    wp = (w // patchSize) * patchSize
    xCrop = x[:, :, :hp, :wp].float()
    patches = xCrop.unfold(2, patchSize, patchSize).unfold(3, patchSize, patchSize)
    spec = torch.fft.fft2(patches, norm="ortho")
    half = patchSize // 2
    hiQuad = spec[..., half:, half:]
    return (hiQuad.real ** 2 + hiQuad.imag ** 2).mean()


def computeLoss(dist, ctx):
    zAdv = dist.mean.float()
    zOrig = ctx.get("zOrigMean", ctx["zTargetMean"])
    step = int(ctx.get("step", 1))
    totalSteps = max(1, int(ctx.get("totalSteps", 100)))

    # Erroneous Timestep Guidance (ETG): simulate purification window t in [1, t_p] vs erroneous high-noise t_err=999
    alphaBarT = math.cos(((step / totalSteps) * 0.25) * math.pi * 0.5) ** 2
    pfgScale = math.exp(alphaBarT - 1.0)
    etgLoss = F.mse_loss(zAdv, -0.85 * zOrig + 0.15 * ctx["zTargetMean"])

    xIn = ctx.get("xIn")
    if xIn is not None:
        hfEnergy = _patchHighFreqEnergy(xIn, patchSize=8)
        return etgLoss - 0.25 * pfgScale * hfEnergy
    return etgLoss
