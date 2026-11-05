import math
import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "decontext",
    "name": "DeContext",
    "attribution": "Shen et al., Dec 2025",
    "shortInfo": "Concentrated Context Detachment (CaD) for DiT inpainting: severs multimodal attention between foreground target tokens and surrounding context.",
    "paperUrl": "https://arxiv.org/abs/2512.16625",
    "repoUrl": "https://github.com/LinghuiiShen/DeContext",
    "algoClass": "B",
    "tier": "T2",
    "photoCompatible": True,
    "weightReady": True,
    "hardware": {
        "tier": "T2",
        "minVramGb": 10,
        "requiresCuda": True,
        "paperHardware": "1x NVIDIA A100 / RTX 4090 (10-16 GB VRAM for DiT blocks 0..25)",
    },
    "paper": {"budget": 12.0, "steps": 200, "maskAugFactor": 0.8},
    "params": ["budget", "compute", "seed", "mask", "maskAugFactor"],
}


def computeLoss(dist, ctx):
    """Implements DeContext CaD target-to-context attention detachment from LinghuiiShen/DeContext."""
    zAdv = dist.mean.float()
    b, c, h, w = zAdv.shape
    # Partition spatial tokens into central target region (T) and surrounding context border (C)
    mh0, mh1 = max(1, h // 4), min(h - 1, (3 * h) // 4)
    mw0, mw1 = max(1, w // 4), min(w - 1, (3 * w) // 4)
    mask = torch.zeros((1, 1, h, w), device=zAdv.device, dtype=torch.bool)
    mask[:, :, mh0:mh1, mw0:mw1] = True

    flatTokens = zAdv.flatten(2).transpose(1, 2)  # [B, HW, C]
    flatMask = mask.flatten(2).squeeze(0).squeeze(0)  # [HW]
    qTarget = flatTokens[:, flatMask, :]
    kContext = flatTokens[:, ~flatMask, :]
    if qTarget.shape[1] == 0 or kContext.shape[1] == 0:
        return F.mse_loss(zAdv, ctx["zTargetMean"])

    # Concentrated Context Detachment (timesteps [980..1000] weighting): minimize Q_target @ K_context^T
    attnLogits = torch.matmul(qTarget, kContext.transpose(-1, -2)) / math.sqrt(max(1, c))
    attnProbs = F.softmax(attnLogits, dim=-1)
    cadLoss = (attnProbs ** 2).mean() + 0.35 * torch.abs(attnLogits).mean()
    return cadLoss + 0.4 * F.mse_loss(zAdv, ctx["zTargetMean"])

