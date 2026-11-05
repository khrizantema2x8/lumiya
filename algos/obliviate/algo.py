import torch.nn.functional as F

ALGO_META = {
    "id": "obliviate",
    "name": "\u25b2 Obliviate (Generator-Side)",
    "attribution": "Shakibania et al., ECCV 2026",
    "shortInfo": "Generator-side LoRA concept unlearning for autoregressive visual token generators (Liquid, Emu3-Gen, Janus-Pro); operates on model weights, not user photos.",
    "paperUrl": "https://arxiv.org/abs/2606.28643",
    "repoUrl": "https://github.com/multimodal-ai-lab/Obliviate",
    "algoClass": "G",
    "tier": "T3",
    "photoCompatible": False,
    "weightReady": False,
    "blockerReason": "Class G generator-side LoRA unlearning: modifies autoregressive generator weights (Liquid, Emu3-Gen, Janus-Pro) rather than perturbing user photographs.",
    "hardware": {
        "tier": "T3",
        "minVramGb": 24,
        "requiresCuda": True,
        "paperHardware": "NVIDIA A100 40-80 GB for autoregressive generator LoRA fine-tuning",
    },
    "paper": {"budget": 8.0, "steps": 100},
    "params": ["budget", "compute", "seed"],
}


def computeLoss(dist, ctx):
    return F.mse_loss(dist.mean.float(), ctx["zTargetMean"])
