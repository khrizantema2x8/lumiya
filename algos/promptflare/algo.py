import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "promptflare",
    "name": "PromptFlare",
    "attribution": "Cross-Attention BOS Token Decoy Defense",
    "shortInfo": "Leverages invariant Beginning-of-Sequence (BOS) cross-attention decoys to neutralize malicious text prompt alignment.",
    "paperUrl": "https://arxiv.org/search/?query=PromptFlare+cross+attention+adversarial+diffusion&searchtype=all",
    "hardware": {"tier": "T2", "minVramGb": 16, "requiresCuda": True, "paperHardware": "Not reported; estimate"},
}


def transformInput(xDef, step, ctx):
    return xDef


def computeLoss(dist, ctx):
    zMean = dist.mean.float()
    bosAnchor = torch.mean(zMean, dim=(2, 3), keepdim=True).expand_as(zMean)
    promptBias = float(ctx.get("promptBias", 1.0))
    return 0.70 * F.mse_loss(zMean, ctx["zTargetMean"]) + 0.30 * promptBias * F.mse_loss(zMean, bosAnchor)

