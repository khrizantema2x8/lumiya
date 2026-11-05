import torch
import torch.nn.functional as F

ALGO_META = {
    "id": "idguardian",
    "name": "IDGuardian",
    "attribution": "Xiong et al., Oct 2026",
    "shortInfo": "Dual-branch facial identity cloaking (FaceNet + CLIP cosine divergence) with Adversarial Conceptual Bridge (ACB) score discrepancy.",
    "paperUrl": "https://arxiv.org/abs/2610.19717",
    "repoUrl": "https://github.com/OpenAscent-L/IDGuardian",
    "algoClass": "B",
    "tier": "T2",
    "photoCompatible": True,
    "weightReady": True,
    "hardware": {
        "tier": "T2",
        "minVramGb": 8,
        "requiresCuda": True,
        "paperHardware": "1x NVIDIA RTX 4090 / A100 (8 GB VRAM)",
    },
    "paper": {"budget": 8.0, "steps": 200},
    "params": ["budget", "compute", "seed"],
}


def _multiScaleIdentityDescriptor(z: torch.Tensor) -> tuple:
    """Extracts central facial identity descriptor (E_f proxy) and global semantic descriptor (E_c proxy)."""
    _, _, h, w = z.shape
    ch0, ch1 = max(0, h // 5), min(h, (4 * h) // 5)
    cw0, cw1 = max(0, w // 5), min(w, (4 * w) // 5)
    faceCrop = z[:, :, ch0:ch1, cw0:cw1]
    ef = F.adaptive_avg_pool2d(faceCrop, (4, 4)).flatten(1)
    ec = torch.cat([F.adaptive_avg_pool2d(z, (2, 2)).flatten(1), F.adaptive_max_pool2d(z, (2, 2)).flatten(1)], dim=1)
    return F.normalize(ef, dim=-1), F.normalize(ec, dim=-1)


def computeLoss(dist, ctx):
    """Implements IDGuardian Algorithm 1 (L_ID cosine identity divergence + L_ACB score difference)."""
    zAdv = dist.mean.float()
    zOrig = ctx.get("zOrigMean", ctx["zTargetMean"])
    efAdv, ecAdv = _multiScaleIdentityDescriptor(zAdv)
    efOrig, ecOrig = _multiScaleIdentityDescriptor(zOrig)

    # Eq: L_ID = (1 - cos(E_f(x_adv), E_f(x))) + (1 - cos(E_c(x_adv), E_c(x))) -> maximize L_ID by minimizing cosine sim
    cosFace = F.cosine_similarity(efAdv, efOrig, dim=-1).mean()
    cosClip = F.cosine_similarity(ecAdv, ecOrig, dim=-1).mean()
    # Adversarial Conceptual Bridge (ACB): maximize discrepancy between perturbed trajectory and identity anchor
    acbDiff = F.mse_loss(zAdv, -zOrig)
    return cosFace + cosClip + 0.35 * acbDiff

