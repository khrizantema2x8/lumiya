"""Plugin template. Copy this folder to algos/<your_id>/ (no leading underscore) and add readmyalgo.md.

The harness owns the optimization loop, image I/O and steganography. A plugin only shapes the attack.
"""
import torch.nn.functional as F

# Must be a plain literal: it is read with ast.literal_eval, without importing this file.
ALGO_META = {
    "id": "example",
    "name": "Example",
    "attribution": "Author, Venue Year",
    "shortInfo": "One sentence on what this algorithm does.",
    "paperUrl": "https://arxiv.org/abs/0000.00000",
    # Tier T0 to T3 per the spec. minVramGb and requiresCuda gate the plugin; paperHardware is shown to users.
    "hardware": {"tier": "T1", "minVramGb": 6, "requiresCuda": True, "paperHardware": "What the paper reports"},
}


def transformInput(xDef, step, ctx):
    """Optional. Receives the BCHW image in [-1, 1]; must return a 4D tensor."""
    return xDef


def computeLoss(dist, ctx):
    """Optional. dist is the VAE posterior; lower loss is better for the attack."""
    return F.mse_loss(dist.mean.float(), ctx["zTargetMean"])
