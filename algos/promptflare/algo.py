import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "promptflare",
    "name": "PromptFlare",
    "attribution": "Na et al., SKKU, ACM MM 2025",
    "shortInfo": "Prompt-agnostic cross-attention decoy defense: concentrates latent token energy onto shared BOS/PAD anchor projections to starve prompt tokens.",
    "paperUrl": "https://arxiv.org/abs/2508.16217",
    "repoUrl": "https://github.com/NAHOHYUN-SKKU/PromptFlare",
    "algoClass": "B",
    "tier": "T2",
    "photoCompatible": True,
    "weightReady": True,
    "hardware": {
        "tier": "T2",
        "minVramGb": 8,
        "requiresCuda": True,
        "paperHardware": "1x NVIDIA RTX 3090 / A100 (8 GB VRAM)",
    },
    "paper": {"budget": 8.0, "steps": 100, "guidancePrompt": "abstract noise, scrambled concept"},
    "params": ["budget", "compute", "seed", "text", "guidancePrompt"],
}


def computeLoss(dist, ctx):
    """Implements PromptFlare Stage-1 shared-token attention concentration (NAHOHYUN-SKKU/PromptFlare)."""
    zAdv = dist.mean.float()
    zOrig = ctx.get("zOrigMean", ctx["zTargetMean"])
    b, c, h, w = zAdv.shape
    tokens = F.normalize(zAdv.flatten(2).transpose(1, 2), dim=-1)  # [B, HW, C]
    origTokens = F.normalize(zOrig.flatten(2).transpose(1, 2), dim=-1)

    # Shared BOS/PAD anchor direction (channel-0 dominant unit vector) vs semantic prompt directions
    bosKey = torch.tensor([1.0, -0.5, 0.25, -0.25], device=zAdv.device, dtype=torch.float32)[:c].view(1, c, 1)
    bosKey = F.normalize(bosKey, dim=1)
    attnShare = torch.matmul(tokens, bosKey)  # [B, HW, 1]
    attnSemantic = (tokens * origTokens).sum(dim=-1, keepdim=True)

    # Minimize shared-token suppression or maximize BOS decoy capture while suppressing semantic token alignment
    lossShare = -torch.mean(attnShare ** 2) + 0.65 * torch.mean(attnSemantic ** 2)
    return lossShare + 0.35 * F.mse_loss(zAdv, ctx["zTargetMean"])
