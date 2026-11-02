import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "fastprotect_tcuap",
    "name": "FastProtect & TC-UAP",
    "attribution": "Universal Adversarial Perturbation & Temporal-Consistent UAP Defense",
    "shortInfo": "Applies distribution-level Universal Adversarial Perturbation (UAP) priors to accelerate spatial and temporal protection.",
    "paperUrl": "https://arxiv.org/search/?query=Universal+Adversarial+Perturbation+Diffusion+Protection&searchtype=all",
    "hardware": {"tier": "T1", "minVramGb": 2, "requiresCuda": False, "paperHardware": "1.7 GB inference; training on A100 about 50 GB"},
}


def transformInput(xDef, step, ctx):
    return xDef


def computeLoss(dist, ctx):
    zMean = dist.mean.float()
    _, _, h, w = zMean.shape
    gy = torch.arange(h, device=zMean.device, dtype=zMean.dtype).view(1, 1, h, 1)
    gx = torch.arange(w, device=zMean.device, dtype=zMean.dtype).view(1, 1, 1, w)
    uapPrior = torch.sin(gy * 1.5708) * torch.cos(gx * 1.5708)
    return 0.70 * F.mse_loss(zMean, ctx["zTargetMean"]) + 0.30 * F.mse_loss(zMean, uapPrior.expand_as(zMean))

