import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "obliviate",
    "name": "Obliviate",
    "attribution": "KL-Supervised Visual Token Distribution Concept Erasure",
    "shortInfo": "Mitigates unauthorized synthesis in autoregressive and diffusion models via KL-divergence supervision over visual token distributions.",
    "paperUrl": "https://arxiv.org/search/?query=Obliviate+concept+erasure+visual+tokens&searchtype=all",
    "hardware": {"tier": "T3", "minVramGb": 40, "requiresCuda": True, "paperHardware": "Not reported; estimate for generator fine-tuning"},
}


def transformInput(xDef, step, ctx):
    return xDef


def computeLoss(dist, ctx):
    zMean = dist.mean.float()
    logProbs = F.log_softmax(zMean.flatten(1), dim=-1)
    uniTarget = torch.full_like(logProbs, 1.0 / logProbs.shape[-1])
    klUniform = F.kl_div(logProbs, uniTarget, reduction="batchmean")
    return F.mse_loss(zMean, ctx["zTargetMean"]) + 0.40 * klUniform

