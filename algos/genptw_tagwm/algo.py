import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "genptw_tagwm",
    "name": "GenPTW & TAG-WM",
    "attribution": "Latent-Space Provenance Watermarking & Tamper Localization",
    "shortInfo": "Embeds a structured dual latent-space provenance watermark for tamper localization and ownership verification.",
    "paperUrl": "https://arxiv.org/search/?query=latent+space+watermarking+tamper+localization+diffusion&searchtype=all",
    "hardware": {"tier": "T2", "minVramGb": 8, "requiresCuda": True, "paperHardware": "Not reported; estimate"},
}


def transformInput(xDef, step, ctx):
    return xDef


def computeLoss(dist, ctx):
    zMean = dist.mean.float()
    _, _, h, w = zMean.shape
    gy = torch.arange(h, device=zMean.device)
    gx = torch.arange(w, device=zMean.device)
    grid = (((gy.unsqueeze(1) + gx.unsqueeze(0)) % 2).float() * 2.0 - 1.0) * 0.65
    wmTarget = grid.unsqueeze(0).unsqueeze(0).expand_as(zMean)
    return 0.60 * F.mse_loss(zMean, ctx["zTargetMean"]) + 0.40 * F.mse_loss(zMean, wmTarget)

