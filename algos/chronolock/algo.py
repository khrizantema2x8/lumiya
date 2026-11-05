import torch.nn.functional as F

ALGO_META = {
    "id": "chronolock",
    "name": "\u25b2 ChronoLock",
    "attribution": "He et al., Jun 2026",
    "shortInfo": "Bi-level temporal LoRA trajectory immunization against MotionDirector video customization (requires 5-frame video sequences & 4x A6000).",
    "paperUrl": "https://arxiv.org/abs/2606.21146",
    "repoUrl": "",
    "algoClass": "D",
    "tier": "T3",
    "photoCompatible": False,
    "weightReady": False,
    "blockerReason": "Requires multi-frame video clips (5-frame sliding windows) and bi-level MotionDirector temporal LoRA training across 4x RTX A6000 GPUs.",
    "hardware": {
        "tier": "T3",
        "minVramGb": 24,
        "requiresCuda": True,
        "paperHardware": "4x NVIDIA RTX A6000 (48 GB each) for bi-level temporal LoRA unrolling",
    },
    "paper": {"budget": 8.0, "steps": 150, "temporalWeight": 0.60},
    "params": ["budget", "compute", "seed", "temporal", "temporalWeight"],
}


def computeLoss(dist, ctx):
    return F.mse_loss(dist.mean.float(), ctx["zTargetMean"])
