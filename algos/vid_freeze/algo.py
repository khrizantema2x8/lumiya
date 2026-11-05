import math
import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "vid_freeze",
    "name": "Vid-Freeze",
    "attribution": "Chowdhury et al., Sep 2025",
    "shortInfo": "Temporal motion freezing for Image-to-Video (I2V): forces frame-0 temporal self-attention dominance and suppresses spatio-temporal motion norms.",
    "paperUrl": "https://arxiv.org/abs/2509.23279",
    "repoUrl": "",
    "algoClass": "E",
    "tier": "T2",
    "photoCompatible": True,
    "weightReady": True,
    "hardware": {
        "tier": "T2",
        "minVramGb": 8,
        "requiresCuda": True,
        "paperHardware": "1x NVIDIA A100 / RTX 4090 (8 GB VRAM)",
    },
    "paper": {"budget": 8.0, "steps": 100, "temporalWeight": 0.50},
    "params": ["budget", "compute", "seed", "temporal", "temporalWeight"],
}


def computeLoss(dist, ctx):
    """Implements Vid-Freeze decoupled Frame-0 temporal domination + coupled spatio-temporal norm suppression (Worksheet M24)."""
    zAdv = dist.mean.float()
    zOrig = ctx.get("zOrigMean", ctx["zTargetMean"])
    tempWeight = float(ctx.get("temporalWeight", 0.50))

    # Synthesize a 4-frame latent pseudo-clip [B, T=4, HW, C] around the first-frame anchor
    b, c, h, w = zAdv.shape
    f0 = zAdv.flatten(2).transpose(1, 2)  # [B, HW, C]
    fOrig = zOrig.flatten(2).transpose(1, 2)
    clip = torch.stack([f0, 0.85 * f0 + 0.15 * fOrig, 0.70 * f0 + 0.30 * fOrig, 0.55 * f0 + 0.45 * fOrig], dim=2)  # [B, HW, T, C]

    # Temporal self-attention across T=4 frames: drive column 0 (Frame-0 anchor) toward 1 and columns 1..T-1 toward 0
    attnTemp = F.softmax(torch.matmul(clip, clip.transpose(-1, -2)) / math.sqrt(max(1, c)), dim=-1)  # [B, HW, T, T]
    targetTemp = torch.zeros_like(attnTemp)
    targetTemp[..., 0] = 1.0
    decoupledFreezeLoss = F.mse_loss(attnTemp, targetTemp)

    # Coupled spatio-temporal norm suppression: minimize variance across spatial tokens so motion fields collapse
    coupledNormLoss = zAdv.var(dim=(-2, -1)).mean()
    return tempWeight * decoupledFreezeLoss + (1.0 - tempWeight) * coupledNormLoss + 0.25 * F.mse_loss(zAdv, ctx["zTargetMean"])
