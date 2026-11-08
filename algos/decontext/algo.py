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
    zOrig = ctx.get("zOrigMean", ctx["zTargetMean"])
    b, c, h, w = zAdv.shape
    # Partition spatial tokens into central target region (T) scaled by maskAugFactor and surrounding context border (C)
    augFactor = max(0.3, min(1.6, float(ctx.get("maskAugFactor", 0.8))))
    halfSpan = max(0.12, min(0.42, 0.25 * augFactor))
    mh0, mh1 = max(1, int(round(h * (0.5 - halfSpan)))), min(h - 1, int(round(h * (0.5 + halfSpan))))
    mw0, mw1 = max(1, int(round(w * (0.5 - halfSpan)))), min(w - 1, int(round(w * (0.5 + halfSpan))))
    mask = torch.zeros((1, 1, h, w), device=zAdv.device, dtype=torch.bool)
    mask[:, :, mh0:mh1, mw0:mw1] = True

    flatAdv = zAdv.flatten(2).transpose(1, 2)  # [B, HW, C]
    flatOrig = zOrig.flatten(2).transpose(1, 2)
    flatMask = mask.flatten(2).squeeze(0).squeeze(0)  # [HW]
    qTarget = flatAdv[:, flatMask, :]
    kContext = flatAdv[:, ~flatMask, :]
    kOrigContext = flatOrig[:, ~flatMask, :]
    if qTarget.shape[1] == 0 or kContext.shape[1] == 0:
        return F.mse_loss(zAdv, ctx["zTargetMean"])

    # Concentrated Context Detachment (timesteps [980..1000]): sever Q_target alignment with both current & clean K_context
    scale = 1.0 / math.sqrt(max(1, c))
    attnLogits = torch.matmul(qTarget, kContext.transpose(-1, -2)) * scale
    attnCleanLogits = torch.matmul(qTarget, kOrigContext.transpose(-1, -2)) * scale
    attnProbs = F.softmax(attnLogits, dim=-1)
    cadLoss = (attnProbs ** 2).mean() + 0.35 * torch.abs(attnCleanLogits).mean()
    return cadLoss + 0.4 * F.mse_loss(zAdv, ctx["zTargetMean"]) - 0.15 * F.l1_loss(zAdv, zOrig)

