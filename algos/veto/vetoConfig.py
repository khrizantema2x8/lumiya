from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass
class VetoParameters:
    """Hyperparameters from Grebe et al. (arXiv:2607.27292v1, Appendix B.2 & Table 7)."""
    targetArch: str = "flux2"                 # "flux2" (1st double block) or "fiboEdit" (first 8 double blocks)
    interactionMode: str = "canvasRef"        # "canvasRef", "refText", "canvasText", "canvasRefPlusRefText"
    hookStage: str = "doubleStream"           # "doubleStream" (default, 0:57) or "singleStream" (ablation, 5:45)
    augmentMode: str = "none"                 # "none", "hFlip", "crop", "jpeg" (Table 5 EOT robustness)
    epsilon255: float = 4.0                   # Paper Pareto optimal on FLUX.2: 4/255 (sweep: 4, 8, 12, 16, 32)
    stepSize255: float = 2.0                  # Paper default: alpha = 2 on [0, 255] scale
    momentumDecay: float = 0.90               # Paper default: tau = 0.9 (Eq. 8)
    optimizationSteps: int = 100              # Paper default: n = 100 steps
    inferenceSteps: int = 10                  # Paper default: 10 Euler flow steps per PGD iteration
    guidanceScale: float = 4.0                # Paper default: Classifier-Free Guidance eta = 4.0
    surrogatePrompt: str = ""                 # Paper default: empty surrogate prompt ""
    stabilityTau: float = 1e-8                # Numerical stability constant in -A * log(A + tau) (Eq. 5)
    workingResolution: int = 512              # Paper default: 512x512 primary resolution
    numTextTokens: int = 64                   # Surrogate text token sequence length |p|
    numHeads: int = 16                        # Attention heads H in local double-stream surrogate
    headDim: int = 64                         # Dimension per attention head d_k

    @property
    def hookedBlockIndices(self) -> Tuple[int, ...]:
        """Returns model-specific double-stream block indices (Appendix B.2)."""
        if self.targetArch == "fiboEdit":
            return (0, 1, 2, 3, 4, 5, 6, 7)
        return (0,)

    @classmethod
    def fromContext(cls, ctx: Dict[str, object]) -> "VetoParameters":
        params = cls()
        if "vetoTargetArch" in ctx:
            params.targetArch = str(ctx["vetoTargetArch"])
        if "vetoInteractionMode" in ctx:
            params.interactionMode = str(ctx["vetoInteractionMode"])
        if "vetoHookStage" in ctx:
            params.hookStage = str(ctx["vetoHookStage"])
        if "vetoAugmentMode" in ctx:
            params.augmentMode = str(ctx["vetoAugmentMode"])
        if "epsilon255" in ctx:
            params.epsilon255 = float(ctx["epsilon255"])
        if "steps" in ctx:
            params.optimizationSteps = int(ctx["steps"])
        if "guidancePrompt" in ctx and str(ctx["guidancePrompt"]).strip():
            params.surrogatePrompt = str(ctx["guidancePrompt"]).strip()
        if "guidanceScale" in ctx:
            params.guidanceScale = float(ctx["guidanceScale"])
        return params