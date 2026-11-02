from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F


def computeBlockEntropy(attnSubBlock: torch.Tensor, stabilityTau: float = 1e-8) -> torch.Tensor:
    """
    Implements Equation (5) from Appendix A.2:
        H(A_{t,l,h}^{a -> b}) = - sum_{i in a} sum_{j in b} A_{t,l,h,ij} * log(A_{t,l,h,ij} + tau)
    CRITICAL: attnSubBlock is sliced directly from the full row-normalized attention matrix A_{t,l,h}
    over Z_t = [p; c_t; x] WITHOUT renormalizing the sub-block, preserving both total attention mass
    assigned to the target group and its spatial distribution.
    Normalizes by query count |a| so gradient scale remains consistent across resolutions before L1 norm.
    """
    clampedBlock = torch.clamp(attnSubBlock.float(), min=0.0, max=1.0)
    entropyElements = -clampedBlock * torch.log(clampedBlock + stabilityTau)
    # Sum over keys j in b and queries i in a, averaged over batch and heads (E_{l,h})
    queryCount = max(1, clampedBlock.shape[-2])
    blockEntropy = entropyElements.sum(dim=(-2, -1)) / float(queryCount)
    return blockEntropy.mean()


def computeBidirectionalVetoObjective(
    fullAttnProbs: torch.Tensor,
    textLen: int,
    canvasLen: int,
    refLen: int,
    interactionMode: str = "canvasRef",
    stabilityTau: float = 1e-8,
) -> torch.Tensor:
    """
    Implements Equation (1) & Equation (6) over joint token sequence Z_t = [p; c_t; x]:
        L_VETO = E_{t,l,h}[ H(A_{t,l,h}^{c -> x}) + H(A_{t,l,h}^{x -> c}) ]
    Also supports the ablation configurations from Table 7(a):
        - "canvasRef"            : H(A^{c -> x}) + H(A^{x -> c})  [Paper Default]
        - "refText"              : H(A^{x -> p}) + H(A^{p -> x})
        - "canvasText"           : H(A^{c -> p}) + H(A^{p -> c})
        - "canvasRefPlusRefText" : H(A^{c -> x}) + H(A^{x -> c}) + H(A^{x -> p}) + H(A^{p -> x})
    fullAttnProbs shape: [B, H, N_total, N_total] where N_total = textLen + canvasLen + refLen,
    row-normalized such that fullAttnProbs.sum(dim=-1) == 1.0.
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

    if interactionMode in ("refText", "canvasRefPlusRefText"):
        attnRefToText = fullAttnProbs[:, :, xStart:xEnd, pStart:pEnd]
        attnTextToRef = fullAttnProbs[:, :, pStart:pEnd, xStart:xEnd]
        totalEntropy = totalEntropy + computeBlockEntropy(attnRefToText, stabilityTau)
        totalEntropy = totalEntropy + computeBlockEntropy(attnTextToRef, stabilityTau)

    if interactionMode == "canvasText":
        attnCanvasToText = fullAttnProbs[:, :, cStart:cEnd, pStart:pEnd]
        attnTextToCanvas = fullAttnProbs[:, :, pStart:pEnd, cStart:cEnd]
        totalEntropy = totalEntropy + computeBlockEntropy(attnCanvasToText, stabilityTau)
        totalEntropy = totalEntropy + computeBlockEntropy(attnTextToCanvas, stabilityTau)

    return totalEntropy


def computeExplicitRowNormalizedAttention(
    queryTensor: torch.Tensor,
    keyTensor: torch.Tensor,
) -> torch.Tensor:
    """
    Computes explicit unfused row-normalized attention probabilities:
        A = softmax((Q @ K^T) / sqrt(d_k), dim=-1)
    Bypasses fused FlashAttention / cudnn SDPA kernels so the full attention probability matrix
    remains differentiable for VETO entropy backpropagation.
    queryTensor, keyTensor shape: [B, H, N_total, d_k]
    """
    headDim = queryTensor.shape[-1]
    scaleFactor = 1.0 / math.sqrt(float(headDim))
    attnLogits = torch.matmul(queryTensor.float(), keyTensor.float().transpose(-2, -1)) * scaleFactor
    attnProbs = F.softmax(attnLogits, dim=-1)
    return attnProbs


class EarlyBlockStopException(Exception):
    """Raised after the last hooked double-stream block finishes to skip unhooked downstream blocks."""


class MmditJointAttentionHookManager:
    """
    Registers lightweight forward hooks on selected MMDiT double-stream (or single-stream) blocks
    for FLUX.2, FIBO-EDIT, or FLUX.1 Kontext models loaded via HuggingFace diffusers.
    Captures explicit row-normalized joint attention probabilities over Z_t = [p; c_t; x]
    and accumulates L_VETO across steps, layers, and heads.
    """

    def __init__(
        self,
        textLen: int,
        canvasLen: int,
        refLen: int,
        interactionMode: str = "canvasRef",
        stabilityTau: float = 1e-8,
        earlyStopAfterLastBlock: bool = True,
    ) -> None:
        self.textLen = textLen
        self.canvasLen = canvasLen
        self.refLen = refLen
        self.interactionMode = interactionMode
        self.stabilityTau = stabilityTau
        self.earlyStopAfterLastBlock = earlyStopAfterLastBlock
        self.recordedEntropies: List[torch.Tensor] = []
        self.handles: List[torch.utils.hooks.RemovableHandle] = []

    def resetStepAccumulator(self) -> None:
        self.recordedEntropies.clear()

    def recordJointQueriesAndKeys(self, queryTensor: torch.Tensor, keyTensor: torch.Tensor) -> None:
        attnProbs = computeExplicitRowNormalizedAttention(queryTensor, keyTensor)
        stepBlockEntropy = computeBidirectionalVetoObjective(
            fullAttnProbs=attnProbs,
            textLen=self.textLen,
            canvasLen=self.canvasLen,
            refLen=self.refLen,
            interactionMode=self.interactionMode,
            stabilityTau=self.stabilityTau,
        )
        self.recordedEntropies.append(stepBlockEntropy)

    def getMeanObjective(self) -> torch.Tensor:
        if not self.recordedEntropies:
            raise RuntimeError("No MMDiT attention matrices were captured by the VETO hooks.")
        return torch.stack(self.recordedEntropies).mean()

    def attachToDiffusersTransformer(
        self,
        transformerModel: nn.Module,
        blockIndices: Tuple[int, ...],
        hookStage: str = "doubleStream",
    ) -> None:
        self.removeHooks()
        blockListAttr = "transformer_blocks" if hookStage == "doubleStream" else "single_transformer_blocks"
        blocksContainer = getattr(transformerModel, blockListAttr, None)
        if blocksContainer is None:
            return

        maxBlockIdx = max(blockIndices) if blockIndices else 0
        for idx in blockIndices:
            if 0 <= idx < len(blocksContainer):
                blockModule = blocksContainer[idx]
                attnModule = getattr(blockModule, "attn", None)
                if attnModule is not None:
                    isLastHooked = (idx == maxBlockIdx) and self.earlyStopAfterLastBlock
                    handle = attnModule.register_forward_hook(self.makeAttnForwardHook(isLastHooked))
                    self.handles.append(handle)

    def makeAttnForwardHook(self, isLastHookedBlock: bool):
        def hookFn(module: nn.Module, args: Tuple[object, ...], kwargs: Dict[str, object], output: object) -> object:
            # Extract hidden_states ([c_t; x]) and encoder_hidden_states (p) from double-stream block args/kwargs
            hiddenStates = kwargs.get("hidden_states", args[0] if len(args) > 0 else None)
            encHiddenStates = kwargs.get("encoder_hidden_states", args[1] if len(args) > 1 else None)

            if isinstance(hiddenStates, torch.Tensor) and hasattr(module, "to_q") and hasattr(module, "to_k"):
                numHeads = getattr(module, "heads", 16)
                qVis = module.to_q(hiddenStates)
                kVis = module.to_k(hiddenStates)
                bsz, visSeqLen, totalDim = qVis.shape
                headDim = totalDim // numHeads
                qVis = qVis.view(bsz, visSeqLen, numHeads, headDim).transpose(1, 2)
                kVis = kVis.view(bsz, visSeqLen, numHeads, headDim).transpose(1, 2)

                if isinstance(encHiddenStates, torch.Tensor) and hasattr(module, "add_q_proj") and module.add_q_proj is not None:
                    qTxt = module.add_q_proj(encHiddenStates)
                    kTxt = module.add_k_proj(encHiddenStates)
                    txtSeqLen = qTxt.shape[1]
                    qTxt = qTxt.view(bsz, txtSeqLen, numHeads, headDim).transpose(1, 2)
                    kTxt = kTxt.view(bsz, txtSeqLen, numHeads, headDim).transpose(1, 2)
                    # Joint sequence ordering Z_t = [p; c_t; x]
                    jointQ = torch.cat([qTxt, qVis], dim=2)
                    jointK = torch.cat([kTxt, kVis], dim=2)
                else:
                    jointQ = qVis
                    jointK = kVis

                self.recordJointQueriesAndKeys(jointQ, jointK)

            if isLastHookedBlock:
                raise EarlyBlockStopException()
            return output

        return hookFn

    def removeHooks(self) -> None:
        for handle in self.handles:
            handle.remove()
        self.handles.clear()