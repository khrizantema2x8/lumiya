import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "anti_i2v",
    "name": "Anti-I2V",
    "attribution": "L*a*b* Perceptual & Frequency-Domain Image-to-Video Disruption",
    "shortInfo": "Disrupts temporal coherence in image-to-video generation via perceptual color-opponent and frequency optimization.",
    "paperUrl": "https://arxiv.org/search/?query=image+to+video+adversarial+defense+temporal+coherence&searchtype=all",
    "hardware": {"tier": "T3", "minVramGb": 40, "requiresCuda": True, "paperHardware": "A100 40 GB"},
}


def transformInput(xDef, step, ctx):
    return xDef


def computeLoss(dist, ctx):
    zMean = dist.mean.float()
    fftCur = torch.fft.rfft2(zMean, norm="ortho")
    fftTarget = ctx.get("fftTargetMean")
    if fftTarget is None:
        fftTarget = torch.fft.rfft2(ctx["zTargetMean"], norm="ortho")
    tempWeight = float(ctx.get("temporalWeight", 0.5))
    oppLoss = F.mse_loss(zMean[:, 1:] - zMean[:, :-1], ctx["zTargetMean"][:, 1:] - ctx["zTargetMean"][:, :-1])
    return F.mse_loss(zMean, ctx["zTargetMean"]) + tempWeight * oppLoss + 0.25 * F.mse_loss(torch.abs(fftCur), torch.abs(fftTarget))

