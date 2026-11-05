"""Plugin template. Copy this folder to algos/<your_id>/ (no leading underscore) and add readmyalgo.md.

The harness owns the optimization loop, native-resolution visibility mask, image I/O and steganography.
A plugin only shapes the input transform and loss objective.
"""
import torch.nn.functional as F

# Must be a plain literal: it is read with ast.literal_eval, without importing this file.
ALGO_META = {
    "id": "example",
    "name": "Example",
    "attribution": "Author et al., Venue Year",
    "shortInfo": "One sentence on what this algorithm does and what threat model it targets.",
    "paperUrl": "https://arxiv.org/abs/0000.00000",
    "repoUrl": "https://github.com/org/repo",
    "algoClass": "A",
    "tier": "T1",
    "photoCompatible": True,
    "weightReady": True,
    "hardware": {"tier": "T1", "minVramGb": 6, "requiresCuda": True, "paperHardware": "What the paper reports"},
    "paper": {"budget": 16.0, "steps": 200},
    "params": ["budget", "compute", "seed"],
}


def transformInput(xDef, step, ctx):
    """Optional. Receives the BCHW image in [-1, 1]; must return a 4D tensor."""
    return xDef


def computeLoss(dist, ctx):
    """Receives the VAE posterior dist and ctx dict; lower loss is minimized by the harness PGD step."""
    return F.mse_loss(dist.mean.float(), ctx["zTargetMean"])
