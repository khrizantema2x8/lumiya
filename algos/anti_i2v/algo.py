import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "anti_i2v",
    "name": "\u25b2 Anti-I2V",
    "attribution": "Vu et al., Mar 2026",
    "shortInfo": "Color-space (CIE Lab a/b chroma) + 25% low-frequency DCT perturbation against Image-to-Video (I2V) diffusion.",
    "paperUrl": "https://arxiv.org/abs/2603.24570",
    "repoUrl": "",
    "algoClass": "E",
    "tier": "T1",
    "photoCompatible": True,
    "weightReady": False,
    "blockerReason": "No official code released; paper Algorithm 1 contains 3 unverified formula contradictions (low-pass DCT applied to clean spectrum, Lab scale mismatch, inverted LPIPS sign).",
    "hardware": {
        "tier": "T1",
        "minVramGb": 6,
        "requiresCuda": True,
        "paperHardware": "1x NVIDIA RTX 4090 (6 GB VRAM)",
    },
    "paper": {"budget": 12.0, "steps": 100},
    "params": ["budget", "compute", "seed"],
}


def transformInput(xDef, step, ctx):
    """Applies 25% low-frequency spectral retention only to the perturbation delta (correcting paper Eq. 7 bug)."""
    xOrig = ctx.get("xOrigWork", xDef)
    delta = xDef - xOrig
    spec = torch.fft.fft2(delta.float(), norm="ortho")
    _, _, h, w = delta.shape
    mask = torch.zeros((1, 1, h, w), device=delta.device, dtype=torch.float32)
    mask[:, :, : max(1, h // 4), : max(1, w // 4)] = 1.0
    deltaLow = torch.fft.ifft2(spec * mask, norm="ortho").real.to(xDef.dtype)
    return torch.clamp(xOrig + deltaLow, -1.0, 1.0)


def computeLoss(dist, ctx):
    zAdv = dist.mean.float()
    return F.mse_loss(zAdv, ctx["zTargetMean"])
