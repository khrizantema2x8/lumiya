import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "blurguard",
    "name": "BlurGuard",
    "attribution": "Jeong et al., Korea University (arXiv:2511.00143)",
    "shortInfo": "Applies differentiable Gaussian smoothing and quantization so perturbations survive blur and JPEG compression.",
    "paperUrl": "https://arxiv.org/abs/2511.00143",
    "hardware": {"tier": "T2", "minVramGb": 8, "requiresCuda": True, "paperHardware": "A100 80 GB; estimate for an encoder objective"},
}


def transformInput(xDef, step, ctx):
    xBlur = F.conv2d(xDef, ctx["blurKernel3"], padding=1, groups=3)
    quant = torch.round(xBlur * 127.5) / 127.5
    return xBlur + (quant - xBlur).detach()


def computeLoss(dist, ctx):
    return F.mse_loss(dist.mean.float(), ctx["zTargetMean"])
