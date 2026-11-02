import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "mirage",
    "name": "MIRAGE",
    "attribution": "Policy & Moderation Classifier Alignment Defense (GPT-Image / Gemini / Grok)",
    "shortInfo": "Aligns image representations with safety-classifier boundary anchors so commercial APIs refuse edit requests.",
    "paperUrl": "https://arxiv.org/search/?query=MIRAGE+adversarial+image+protection&searchtype=all",
    "hardware": {"tier": "T3", "minVramGb": 40, "requiresCuda": True, "paperHardware": "Not reported; estimate for a large encoder ensemble"},
}


def transformInput(xDef, step, ctx):
    _, _, height, width = xDef.shape
    scale = float(ctx.get("geoAnchorLow", 1.7))
    downH = max(8, int(round(height / max(scale, 1.1) / 8.0)) * 8)
    downW = max(8, int(round(width / max(scale, 1.1) / 8.0)) * 8)
    xLow = F.interpolate(xDef, size=(downH, downW), mode="bilinear", align_corners=False)
    xUp = F.interpolate(xLow, size=(height, width), mode="bilinear", align_corners=False)
    return 0.72 * xDef + 0.28 * xUp


def computeLoss(dist, ctx):
    zMean = dist.mean.float()
    fftCur = torch.fft.rfft2(zMean, norm="ortho")
    fftTarget = ctx.get("fftTargetMean")
    if fftTarget is None:
        fftTarget = torch.fft.rfft2(ctx["zTargetMean"], norm="ortho")
    specLoss = F.mse_loss(torch.abs(fftCur), torch.abs(fftTarget))
    promptBias = ctx.get("promptBias", 1.0)
    return promptBias * F.mse_loss(zMean, ctx["zTargetMean"]) + 0.35 * specLoss
