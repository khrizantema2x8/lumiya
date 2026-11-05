import math
import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "blurguard",
    "name": "BlurGuard",
    "attribution": "Kim et al., KAIST, NeurIPS 2025",
    "shortInfo": "Region-adaptive optical blur target with 2D radial FFT power spectral density (PSD) log-ratio regularization so perturbations stay invisible in the frequency domain.",
    "paperUrl": "https://arxiv.org/abs/2511.00143",
    "repoUrl": "https://github.com/jsu-kim/BlurGuard",
    "algoClass": "A",
    "tier": "T1",
    "photoCompatible": True,
    "weightReady": True,
    "hardware": {
        "tier": "T1",
        "minVramGb": 6,
        "requiresCuda": False,
        "paperHardware": "1x NVIDIA RTX 3090 (~6 GB VRAM)",
    },
    "paper": {"budget": 8.0, "steps": 200},
    "params": ["budget", "compute", "seed"],
}


def _depthwiseGaussianBlur(x: torch.Tensor, sigma: float = 2.8, kernelSize: int = 11) -> torch.Tensor:
    coords = torch.arange(kernelSize, device=x.device, dtype=x.dtype) - (kernelSize - 1) / 2.0
    g1d = torch.exp(-(coords ** 2) / (2.0 * (sigma ** 2)))
    g1d = g1d / g1d.sum()
    k2d = torch.outer(g1d, g1d).view(1, 1, kernelSize, kernelSize).repeat(x.shape[1], 1, 1, 1)
    pad = kernelSize // 2
    return F.conv2d(F.pad(x, (pad, pad, pad, pad), mode="reflect"), k2d, groups=x.shape[1])


def _radialPsdLogRatioLoss(xAdv: torch.Tensor, xOrig: torch.Tensor, numBins: int = 24) -> torch.Tensor:
    """Computes radial 2D FFT power spectral density log-ratio regularizer from jsu-kim/BlurGuard."""
    eps = 1e-8
    fftAdv = torch.fft.fftshift(torch.fft.fft2(xAdv.float(), norm="ortho"), dim=(-2, -1))
    fftOrig = torch.fft.fftshift(torch.fft.fft2(xOrig.float(), norm="ortho"), dim=(-2, -1))
    psdAdv = (fftAdv.real ** 2 + fftAdv.imag ** 2).mean(dim=1) + eps
    psdOrig = (fftOrig.real ** 2 + fftOrig.imag ** 2).mean(dim=1) + eps

    h, w = psdAdv.shape[-2:]
    yy = torch.linspace(-1.0, 1.0, h, device=xAdv.device).view(h, 1)
    xx = torch.linspace(-1.0, 1.0, w, device=xAdv.device).view(1, w)
    radius = torch.sqrt(yy ** 2 + xx ** 2)
    # Focus regularizer on mid-to-high radial frequencies where adversarial ringing is most perceptible
    highFreqMask = (radius >= 0.25).float().unsqueeze(0)
    logRatio = torch.abs(torch.log10(psdAdv) - torch.log10(psdOrig)) * highFreqMask
    return logRatio.mean()


def computeLoss(dist, ctx):
    zAdv = dist.mean.float()
    zOrig = ctx.get("zOrigMean", ctx["zTargetMean"])
    # Stage-1 & Stage-2 optical blur latent target: smooths high-frequency latent details toward defocus manifold
    zBlurTarget = _depthwiseGaussianBlur(zOrig, sigma=2.2, kernelSize=7)
    latentBlurLoss = F.mse_loss(zAdv, zBlurTarget)

    xIn = ctx.get("xIn")
    xOrigWork = ctx.get("xOrigWork")
    if xIn is not None and xOrigWork is not None:
        psdReg = _radialPsdLogRatioLoss(xIn, xOrigWork)
        return latentBlurLoss + 0.15 * psdReg
    return latentBlurLoss
