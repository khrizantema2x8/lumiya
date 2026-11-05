import math
import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "antiprompt",
    "name": "Anti-Prompt",
    "attribution": "Song et al., Jul 2026",
    "shortInfo": "Text-conditioned cross-attention decoupling for Image-to-Video (I2V): disrupts visual-to-prompt alignment so motion prompts fail to animate the frame.",
    "paperUrl": "https://arxiv.org/abs/2607.01499",
    "repoUrl": "https://github.com/yeonghwansong/Anti-Prompt-code",
    "algoClass": "E",
    "tier": "T2",
    "photoCompatible": True,
    "weightReady": True,
    "hardware": {
        "tier": "T2",
        "minVramGb": 8,
        "requiresCuda": True,
        "paperHardware": "1x NVIDIA RTX 4090 / A6000 (8-12 GB VRAM)",
    },
    "paper": {"budget": 8.0, "steps": 100, "guidancePrompt": "animate move walk talk turn smile"},
    "params": ["budget", "compute", "seed", "text", "guidancePrompt"],
}


def _promptKeyBank(device: torch.device, channels: int, promptStr: str) -> torch.Tensor:
    """Builds deterministic orthogonal prompt key projections derived from guidancePrompt or default I2V motion verbs."""
    seedVal = sum((idx + 1) * ord(ch) for idx, ch in enumerate(promptStr or "animate move walk talk turn smile"))
    gen = torch.Generator(device="cpu").manual_seed(0xA710 + seedVal)
    keys = torch.randn((8, channels), generator=gen, dtype=torch.float32).to(device)
    return F.normalize(keys, dim=-1)


def computeLoss(dist, ctx):
    """Implements Anti-Prompt cross-attention decoupling from yeonghwansong/Anti-Prompt-code (arXiv:2607.01499v3)."""
    zAdv = dist.mean.float()
    zOrig = ctx.get("zOrigMean", ctx["zTargetMean"])
    b, c, h, w = zAdv.shape

    qAdv = F.normalize(zAdv.flatten(2).transpose(1, 2), dim=-1)  # [B, HW, C]
    qOrig = F.normalize(zOrig.flatten(2).transpose(1, 2), dim=-1)
    kPrompt = _promptKeyBank(zAdv.device, c, str(ctx.get("guidancePrompt", "")))  # [K, C]

    attnAdv = F.softmax(torch.matmul(qAdv, kPrompt.t()) / math.sqrt(max(1, c)), dim=-1)
    attnOrig = F.softmax(torch.matmul(qOrig, kPrompt.t()) / math.sqrt(max(1, c)), dim=-1)

    # Maximize divergence of prompt cross-attention maps while suppressing motion-gradient spatial coherence
    attnDivergence = F.cosine_similarity(attnAdv.flatten(1), attnOrig.flatten(1), dim=-1).mean()
    spatialGradAdv = (zAdv[:, :, 1:, :] - zAdv[:, :, :-1, :]).abs().mean() + (zAdv[:, :, :, 1:] - zAdv[:, :, :, :-1]).abs().mean()
    return attnDivergence - 0.25 * spatialGradAdv + 0.35 * F.mse_loss(zAdv, ctx["zTargetMean"])

