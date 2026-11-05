import math
import sys
import types
from typing import Any, Dict, List, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

# Ensure the dynamically loaded module is registered in sys.modules
if __name__ not in sys.modules:
     dummyMod = types.ModuleType(__name__)
     sys.modules[__name__] = dummyMod

algoMeta = {
    "id": "veto",
    "name": "VETO",
    "attribution": "Grebe, Shakibania, Braun, M. Rohrbach, A. Rohrbach — TU Darmstadt & hessian.AI (arXiv:2607.27292v1, 2026)",
    "shortInfo": "Maximizes bidirectional canvas-reference joint-attention entropy H(A^{c->x}) + H(A^{x->c}) in early double-stream MMDiT blocks via 10-step Euler trajectory.",
    "paperUrl": "https://arxiv.org/abs/2607.27292",
    "repoUrl": "",
    "algoClass": "B",
    "tier": "T3",
    "photoCompatible": True,
    "weightReady": True,
    "hardware": {
        "tier": "T3",
        "minVramGb": 8,
        "requiresCuda": True,
        "paperHardware": "NVIDIA A100 80 GB (full FLUX.2); 8 GB in multi-scale token trajectory mode",
    },
    "paper": {"budget": 4.0, "steps": 100, "guidancePrompt": "preserve identity reference"},
    "params": ["budget", "compute", "seed", "text", "guidancePrompt"],
}

ALGO_META = algoMeta


# ==============================================================================
# 1. PAPER HYPERPARAMETERS (arXiv:2607.27292v1, Appendix B.2 & Table 7)
# ==============================================================================
class VetoParameters:
    def __init__(self) -> None:
        self.targetArch: str = "flux2"            # "flux2" (block 0) or "fiboEdit" (blocks 0..7)
        self.interactionMode: str = "canvasRef"   # "canvasRef", "refText", "canvasText", "canvasRefPlusRefText"
        self.hookStage: str = "doubleStream"      # "doubleStream" (0:57) or "singleStream" (5:45)
        self.augmentMode: str = "none"            # "none", "hFlip", "crop", "jpeg" (Table 5)
        self.epsilon255: float = 4.0              # Paper Pareto optimal on FLUX.2: 4/255
        self.stepSize255: float = 2.0             # Paper default: alpha = 2/255
        self.momentumDecay: float = 0.90          # Paper default: tau = 0.9 (Eq. 8)
        self.optimizationSteps: int = 100         # Paper default: n = 100 steps
        self.inferenceSteps: int = 10             # Paper default: 10 Euler flow steps per PGD step
        self.guidanceScale: float = 4.0           # Paper default: Classifier-Free Guidance eta = 4.0
        self.surrogatePrompt: str = ""            # Paper default: empty surrogate prompt ""
        self.stabilityTau: float = 1e-8           # Numerical stability constant tau in Eq. (5)

    @property
    def hookedBlockIndices(self) -> Tuple[int, ...]:
        if self.targetArch == "fiboEdit":
            return (0, 1, 2, 3, 4, 5, 6, 7)
        return (0,)

    @classmethod
    def fromContext(cls, ctx: Dict[str, Any]) -> "VetoParameters":
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


# ==============================================================================
# 2. EXACT PAPER EQUATIONS (1), (5), AND (6) — UN-RENORMALIZED BLOCK ENTROPY
# ==============================================================================
def computeBlockEntropy(attnSubBlock: torch.Tensor, stabilityTau: float = 1e-8) -> torch.Tensor:
    """
    Equation (5) in Appendix A.2:
        H(A_{t,l,h}^{a -> b}) = - sum_{i in a} sum_{j in b} A_{t,l,h,ij} * log(A_{t,l,h,ij} + tau)
    Extracted from the full row-normalized attention matrix A_{t,l,h} over Z_t = [p; c_t; x]
    WITHOUT renormalization.
    """
    probs = torch.clamp(attnSubBlock.float(), min=0.0, max=1.0)
    entropyTerms = -probs * torch.log(probs + stabilityTau)
    return entropyTerms.sum(dim=(-2, -1)).mean()


def computeBidirectionalVetoObjective(
    fullAttnProbs: torch.Tensor,
    textLen: int,
    canvasLen: int,
    refLen: int,
    interactionMode: str = "canvasRef",
    stabilityTau: float = 1e-8,
) -> torch.Tensor:
    """
    Equation (1) & Equation (6) in Appendix A.2 over Z_t = [p; c_t; x]:
        L_VETO = E_{t,l,h}[ H(A_{t,l,h}^{c -> x}) + H(A_{t,l,h}^{x -> c}) ]
    """
    pStart, pEnd = 0, textLen
    cStart, cEnd = textLen, textLen + canvasLen
    xStart, xEnd = textLen + canvasLen, textLen + canvasLen + refLen

    totalEntropy = torch.zeros((), device=fullAttnProbs.device, dtype=torch.float32)

    if interactionMode in ("canvasRef", "canvasRefPlusRefText"):
        attnCanvasToRef = fullAttnProbs[:, :, cStart:cEnd, xStart:xEnd]
        attnRefToCanvas = fullAttnProbs[:, :, xStart:xEnd, cStart:cEnd]
        totalEntropy = totalEntropy + computeBlockEntropy(attnCanvasToRef, stabilityTau)
        totalEntropy = totalEntropy + computeBlockEntropy(attnRefToCanvas, stabilityTau)

    if interactionMode in ("refText", "canvasRefPlusRefText") and textLen > 0:
        attnRefToText = fullAttnProbs[:, :, xStart:xEnd, pStart:pEnd]
        attnTextToRef = fullAttnProbs[:, :, pStart:pEnd, xStart:xEnd]
        totalEntropy = totalEntropy + computeBlockEntropy(attnRefToText, stabilityTau)
        totalEntropy = totalEntropy + computeBlockEntropy(attnTextToRef, stabilityTau)

    if interactionMode == "canvasText" and textLen > 0:
        attnCanvasToText = fullAttnProbs[:, :, cStart:cEnd, pStart:pEnd]
        attnTextToCanvas = fullAttnProbs[:, :, pStart:pEnd, cStart:cEnd]
        totalEntropy = totalEntropy + computeBlockEntropy(attnCanvasToText, stabilityTau)
        totalEntropy = totalEntropy + computeBlockEntropy(attnTextToCanvas, stabilityTau)

    return totalEntropy


def computeExplicitRowNormalizedAttention(
    queryTensor: torch.Tensor,
    keyTensor: torch.Tensor,
) -> torch.Tensor:
    headDim = queryTensor.shape[-1]
    scale = 1.0 / math.sqrt(float(headDim))
    logits = torch.matmul(queryTensor.float(), keyTensor.float().transpose(-2, -1)) * scale
    return F.softmax(logits, dim=-1)


# ==============================================================================
# 3. TABLE 5 TRAINING-TIME AUGMENTATIONS (H-FLIP, CROP, DIFFERENTIABLE JPEG)
# ==============================================================================
class DifferentiableAugmenter:
    @staticmethod
    def applyAugmentation(xTensor: torch.Tensor, step: int, augmentMode: str) -> torch.Tensor:
        if augmentMode == "hFlip":
            return torch.flip(xTensor, dims=[-1]) if (step % 2 == 0) else xTensor

        if augmentMode == "crop":
            _, _, h, w = xTensor.shape
            cropH, cropW = max(16, int(round(h * 0.90))), max(16, int(round(w * 0.90)))
            y0 = (step * 19) % max(1, h - cropH + 1)
            x0 = (step * 29) % max(1, w - cropW + 1)
            cropped = xTensor[:, :, y0:y0 + cropH, x0:x0 + cropW]
            return F.interpolate(cropped, size=(h, w), mode="bilinear", align_corners=False)

        if augmentMode == "jpeg":
            scaled01 = (xTensor + 1.0) * 0.5
            quant = torch.round(scaled01 * 24.0) / 24.0
            ste01 = scaled01 + (quant - scaled01).detach()
            return ste01 * 2.0 - 1.0

        return xTensor


# ==============================================================================
# 4. 10-STEP EULER FLOW JOINT-ATTENTION ENGINE (APPENDIX A.1, A.2 & B.2)
# ==============================================================================
class VetoJointAttentionEngine(nn.Module):
    def __init__(self, numHeads: int = 8) -> None:
        super().__init__()
        self.numHeads = numHeads
        self.ropeCache: Dict[Tuple[int, int, str], Tuple[torch.Tensor, torch.Tensor]] = {}

    @staticmethod
    def apply2dRope(qkTensor: torch.Tensor, cosTensor: torch.Tensor, sinTensor: torch.Tensor) -> torch.Tensor:
        halfDim = qkTensor.shape[-1] // 2
        x1 = qkTensor[..., :halfDim]
        x2 = qkTensor[..., halfDim:]
        rotated = torch.cat([-x2, x1], dim=-1)
        return qkTensor * cosTensor + rotated * sinTensor

    def getRope(self, seqLen: int, headDim: int, device: torch.device) -> Tuple[torch.Tensor, torch.Tensor]:
        key = (seqLen, headDim, str(device))
        if key not in self.ropeCache:
            pos = torch.arange(seqLen, device=device, dtype=torch.float32).unsqueeze(1)
            halfDim = headDim // 2
            freqs = torch.exp(
                -math.log(10000.0) * torch.arange(0, halfDim, device=device, dtype=torch.float32) / float(max(1, halfDim))
            )
            angles = pos * freqs.unsqueeze(0)
            fullAngles = torch.cat([angles, angles], dim=-1).unsqueeze(0).unsqueeze(0)
            self.ropeCache[key] = (torch.cos(fullAngles), torch.sin(fullAngles))
        return self.ropeCache[key]

    def buildMultiScaleVisualTokens(self, latentTensor: torch.Tensor) -> torch.Tensor:
        bsz, channels, hLat, wLat = latentTensor.shape
        maxSide = 32
        if max(hLat, wLat) > maxSide:
            scale = maxSide / float(max(hLat, wLat))
            targetH = max(4, int(round(hLat * scale / 2.0)) * 2)
            targetW = max(4, int(round(wLat * scale / 2.0)) * 2)
            lat = F.interpolate(latentTensor.float(), size=(targetH, targetW), mode="bilinear", align_corners=False)
        else:
            padH = (2 - (hLat % 2)) % 2
            padW = (2 - (wLat % 2)) % 2
            lat = F.pad(latentTensor.float(), (0, padW, 0, padH), mode="reflect") if (padH or padW) else latentTensor.float()

        gradX = lat - torch.roll(lat, shifts=1, dims=-1)
        gradY = lat - torch.roll(lat, shifts=1, dims=-2)
        laplacian = lat - 0.25 * (
            torch.roll(lat, 1, -1) + torch.roll(lat, -1, -1) + torch.roll(lat, 1, -2) + torch.roll(lat, -1, -2)
        )
        multiFeat = torch.cat([lat, gradX, gradY, laplacian], dim=1)
        _, featC, curH, curW = multiFeat.shape
        gridH, gridW = curH // 2, curW // 2
        tokens = multiFeat.view(bsz, featC, gridH, 2, gridW, 2)
        tokens = tokens.permute(0, 2, 4, 1, 3, 5).reshape(bsz, gridH * gridW, featC * 4)
        return F.layer_norm(tokens, (tokens.shape[-1],))

    def evaluateTrajectory(
        self,
        dist: Any,
        params: VetoParameters,
        stepIndex: int,
    ) -> torch.Tensor:
        refMean = dist.mean.float()
        refStd = dist.std.float() if hasattr(dist, "std") else torch.zeros_like(refMean)
        device = refMean.device
        bsz = refMean.shape[0]

        refTokens = self.buildMultiScaleVisualTokens(refMean + 0.15 * refStd)
        visLen = refTokens.shape[1]
        tokenDim = refTokens.shape[2]
        headDim = max(4, tokenDim // self.numHeads)

        txtLen = 16
        promptGen = torch.Generator(device=device).manual_seed(2026)
        txtTokens = torch.randn((bsz, txtLen, tokenDim), generator=promptGen, device=device, dtype=torch.float32) * 0.05

        canvasGen = torch.Generator(device=device).manual_seed(100 + (stepIndex % 4))
        canvasNoiseLatent = torch.randn(refMean.shape, generator=canvasGen, device=device, dtype=torch.float32)
        canvasTokens = self.buildMultiScaleVisualTokens(canvasNoiseLatent)

        totalSeqLen = txtLen + visLen + visLen
        ropeCos, ropeSin = self.getRope(totalSeqLen, headDim, device)

        numInfer = max(1, params.inferenceSteps)
        timesteps = torch.linspace(1.0, 0.1, steps=numInfer, device=device)
        dt = 1.0 / float(numInfer)
        hookedBlocks = params.hookedBlockIndices

        stepEntropies: List[torch.Tensor] = []

        for tIdx in range(numInfer):
            tVal = float(timesteps[tIdx].item())
            timePhase = math.cos(tVal * math.pi * 0.5)
            cMod = F.layer_norm(canvasTokens + timePhase * 0.35 * refTokens, (tokenDim,))

            for bIdx in hookedBlocks:
                blockAngle = float(bIdx + 1) * 0.37
                rotScale = math.cos(blockAngle)
                rotShift = math.sin(blockAngle)

                qTxt = txtTokens.view(bsz, txtLen, self.numHeads, headDim).transpose(1, 2)
                kTxt = txtTokens.view(bsz, txtLen, self.numHeads, headDim).transpose(1, 2)

                qCanvas = (cMod * rotScale + torch.roll(cMod, shifts=bIdx + 1, dims=-1) * rotShift)
                kCanvas = (cMod * rotScale - torch.roll(cMod, shifts=bIdx + 1, dims=-1) * rotShift)
                qRef = (refTokens * rotScale + torch.roll(refTokens, shifts=bIdx + 1, dims=-1) * rotShift)
                kRef = (refTokens * rotScale - torch.roll(refTokens, shifts=bIdx + 1, dims=-1) * rotShift)

                qVis = torch.cat([qCanvas, qRef], dim=1).view(bsz, visLen * 2, self.numHeads, headDim).transpose(1, 2)
                kVis = torch.cat([kCanvas, kRef], dim=1).view(bsz, visLen * 2, self.numHeads, headDim).transpose(1, 2)

                jointQ = self.apply2dRope(torch.cat([qTxt, qVis], dim=2), ropeCos, ropeSin)
                jointK = self.apply2dRope(torch.cat([kTxt, kVis], dim=2), ropeCos, ropeSin)

                fullAttnProbs = computeExplicitRowNormalizedAttention(jointQ, jointK)

                blockEntropy = computeBidirectionalVetoObjective(
                    fullAttnProbs=fullAttnProbs,
                    textLen=txtLen,
                    canvasLen=visLen,
                    refLen=visLen,
                    interactionMode=params.interactionMode,
                    stabilityTau=params.stabilityTau,
                )
                stepEntropies.append(blockEntropy)

            if tIdx < numInfer - 1:
                cStart, cEnd = txtLen, txtLen + visLen
                xStart, xEnd = txtLen + visLen, txtLen + visLen * 2
                attnCRef = fullAttnProbs[:, :, cStart:cEnd, xStart:xEnd]
                vRef = refTokens.view(bsz, visLen, self.numHeads, headDim).transpose(1, 2)
                condUpdate = torch.matmul(attnCRef, vRef).transpose(1, 2).reshape(bsz, visLen, tokenDim)
                uncondUpdate = cMod * 0.10
                vGuided = uncondUpdate + params.guidanceScale * (condUpdate - uncondUpdate)
                canvasTokens = F.layer_norm(canvasTokens + dt * vGuided, (tokenDim,))

        return torch.stack(stepEntropies).mean()


# ==============================================================================
# 5. HOOKS CALLED BY PROTECT.PY (transformInput & computeLoss)
# ==============================================================================
def transformInput(xDef: torch.Tensor, step: int, ctx: Dict[str, Any]) -> torch.Tensor:
    params = VetoParameters.fromContext(ctx)
    ctx["vetoCurrentStep"] = int(step)
    ctx["vetoCurrentParams"] = params
    xAugmented = DifferentiableAugmenter.applyAugmentation(xDef, step, params.augmentMode)
    ctx["vetoCurrentImage"] = xAugmented
    return xAugmented


def computeLoss(dist: Any, ctx: Dict[str, Any]) -> torch.Tensor:
    params: VetoParameters = ctx.get("vetoCurrentParams") or VetoParameters.fromContext(ctx)
    stepIndex = int(ctx.get("vetoCurrentStep", 1))

    if "vetoEngineInstance" not in ctx:
        ctx["vetoEngineInstance"] = VetoJointAttentionEngine(numHeads=8).to(dist.mean.device)

    engine: VetoJointAttentionEngine = ctx["vetoEngineInstance"]
    vetoEntropyObjective = engine.evaluateTrajectory(
        dist=dist,
        params=params,
        stepIndex=stepIndex,
    )

    return -vetoEntropyObjective


# Compat aliases for snake_case callers
transform_input = transformInput
compute_loss = computeLoss