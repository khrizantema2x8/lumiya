from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

from vetoConfig import VetoParameters
from vetoHooks import (
    EarlyBlockStopException,
    MmditJointAttentionHookManager,
    computeBidirectionalVetoObjective,
    computeExplicitRowNormalizedAttention,
)


class DifferentiableAugmenter:
    """Implements training-time transformations from Paper Table 5 (Clean, H-flip, JPEG, Crop)."""

    @staticmethod
    def applyAugmentation(xTensor: torch.Tensor, step: int, augmentMode: str) -> torch.Tensor:
        if augmentMode == "hFlip":
            if step % 2 == 0:
                return torch.flip(xTensor, dims=[-1])
            return xTensor

        if augmentMode == "crop":
            _, _, height, width = xTensor.shape
            cropFrac = 0.90
            cropH = max(16, int(round(height * cropFrac)))
            cropW = max(16, int(round(width * cropFrac)))
            y0 = (step * 19) % max(1, height - cropH + 1)
            x0 = (step * 29) % max(1, width - cropW + 1)
            cropped = xTensor[:, :, y0:y0 + cropH, x0:x0 + cropW]
            return F.interpolate(cropped, size=(height, width), mode="bilinear", align_corners=False)

        if augmentMode == "jpeg":
            # Differentiable Straight-Through Estimator simulating lossy quantization
            scaled01 = (xTensor + 1.0) * 0.5
            quantStep = 24.0
            quantized = torch.round(scaled01 * quantStep) / quantStep
            ste01 = scaled01 + (quantized - scaled01).detach()
            return ste01 * 2.0 - 1.0

        return xTensor


class DoubleStreamJointBlock(nn.Module):
    """
    Architectural Double-Stream MMDiT Block (Appendix A.1):
    Maintains separate normalization, QKV projections, and MLPs for the textual stream (p)
    and visual stream ([c_t; x]), while computing joint attention over concatenated Z_t = [p; c_t; x].
    """

    def __init__(self, hiddenDim: int, numHeads: int, headDim: int, seedIndex: int) -> None:
        super().__init__()
        self.hiddenDim = hiddenDim
        self.numHeads = numHeads
        self.headDim = headDim
        innerDim = numHeads * headDim

        gen = torch.Generator().manual_seed(1337 + seedIndex * 101)
        self.txtQProj = nn.Linear(hiddenDim, innerDim, bias=False)
        self.txtKProj = nn.Linear(hiddenDim, innerDim, bias=False)
        self.txtVProj = nn.Linear(hiddenDim, innerDim, bias=False)
        self.txtOutProj = nn.Linear(innerDim, hiddenDim, bias=False)

        self.visQProj = nn.Linear(hiddenDim, innerDim, bias=False)
        self.visKProj = nn.Linear(hiddenDim, innerDim, bias=False)
        self.visVProj = nn.Linear(hiddenDim, innerDim, bias=False)
        self.visOutProj = nn.Linear(innerDim, hiddenDim, bias=False)

        self.timeModProj = nn.Linear(hiddenDim, hiddenDim * 2, bias=True)

        with torch.no_grad():
            for layer in (
                self.txtQProj, self.txtKProj, self.txtVProj, self.txtOutProj,
                self.visQProj, self.visKProj, self.visVProj, self.visOutProj,
                self.timeModProj,
            ):
                nn.init.orthogonal_(layer.weight, generator=gen)
                if layer.bias is not None:
                    nn.init.zeros_(layer.bias)
                for param in layer.parameters():
                    param.requires_grad = False

    @staticmethod
    def rmsNorm(tensor: torch.Tensor, eps: float = 1e-6) -> torch.Tensor:
        variance = tensor.float().pow(2).mean(dim=-1, keepdim=True)
        return (tensor.float() * torch.rsqrt(variance + eps)).to(tensor.dtype)

    @staticmethod
    def apply2dRope(qkTensor: torch.Tensor, ropeCos: torch.Tensor, ropeSin: torch.Tensor) -> torch.Tensor:
        # qkTensor: [B, H, N, D], ropeCos/ropeSin: [1, 1, N, D]
        halfDim = qkTensor.shape[-1] // 2
        x1 = qkTensor[..., :halfDim]
        x2 = qkTensor[..., halfDim:]
        rotated = torch.cat([-x2, x1], dim=-1)
        return qkTensor * ropeCos + rotated * ropeSin

    def forward(
        self,
        txtTokens: torch.Tensor,
        visTokens: torch.Tensor,
        timeEmb: torch.Tensor,
        ropeCos: torch.Tensor,
        ropeSin: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        bsz = visTokens.shape[0]
        txtLen = txtTokens.shape[1]
        visLen = visTokens.shape[1]

        shiftVis, scaleVis = self.timeModProj(timeEmb).chunk(2, dim=-1)
        normTxt = self.rmsNorm(txtTokens)
        normVis = self.rmsNorm(visTokens) * (1.0 + scaleVis.unsqueeze(1)) + shiftVis.unsqueeze(1)

        qTxt = self.txtQProj(normTxt).view(bsz, txtLen, self.numHeads, self.headDim).transpose(1, 2)
        kTxt = self.txtKProj(normTxt).view(bsz, txtLen, self.numHeads, self.headDim).transpose(1, 2)
        vTxt = self.txtVProj(normTxt).view(bsz, txtLen, self.numHeads, self.headDim).transpose(1, 2)

        qVis = self.visQProj(normVis).view(bsz, visLen, self.numHeads, self.headDim).transpose(1, 2)
        kVis = self.visKProj(normVis).view(bsz, visLen, self.numHeads, self.headDim).transpose(1, 2)
        vVis = self.visVProj(normVis).view(bsz, visLen, self.numHeads, self.headDim).transpose(1, 2)

        # Concatenated sequence Z_t = [p; c_t; x]
        jointQ = torch.cat([qTxt, qVis], dim=2)
        jointK = torch.cat([kTxt, kVis], dim=2)
        jointV = torch.cat([vTxt, vVis], dim=2)

        jointQ = self.apply2dRope(jointQ, ropeCos, ropeSin)
        jointK = self.apply2dRope(jointK, ropeCos, ropeSin)

        # Explicit unfused row-normalized attention matrix A_{t,l,h}
        attnProbs = computeExplicitRowNormalizedAttention(jointQ, jointK)

        jointOut = torch.matmul(attnProbs.to(jointV.dtype), jointV)
        jointOut = jointOut.transpose(1, 2).reshape(bsz, txtLen + visLen, self.numHeads * self.headDim)

        outTxt = txtTokens + self.txtOutProj(jointOut[:, :txtLen, :])
        outVis = visTokens + self.visOutProj(jointOut[:, txtLen:, :])
        return outTxt, outVis, attnProbs


class LocalDoubleStreamMmditSurrogate(nn.Module):
    """
    VRAM-efficient Double-Stream MMDiT Surrogate implementing Appendix A.1 & B.2:
    - Patchifies 2x2 latent grids into visual tokens for canvas c_t and reference image x = E_img(x).
    - Evolves canvas c_t over 10 FlowMatchEulerDiscreteScheduler steps from c_0 ~ N(0, 1)
      with empty surrogate prompt p and Classifier-Free Guidance scale eta = 4.0.
    - Evaluates Equation (5) and Equation (6) on the hooked double-stream blocks
      (Block 0 for FLUX.2, Blocks 0..7 for FIBO-EDIT).
    """

    def __init__(self, latentChannels: int = 4, numBlocks: int = 8, numHeads: int = 16, headDim: int = 32) -> None:
        super().__init__()
        self.latentChannels = latentChannels
        self.patchSize = 2
        self.patchDim = latentChannels * (self.patchSize ** 2)
        self.hiddenDim = numHeads * headDim
        self.numHeads = numHeads
        self.headDim = headDim

        gen = torch.Generator().manual_seed(20260729)
        self.visInProj = nn.Linear(self.patchDim, self.hiddenDim, bias=True)
        self.visOutProj = nn.Linear(self.hiddenDim, self.patchDim, bias=True)

        # Fixed empty-prompt token embedding p = E_text("")
        self.emptyPromptTokens = nn.Parameter(
            torch.randn(1, 32, self.hiddenDim, generator=gen) * 0.02,
            requires_grad=False,
        )

        with torch.no_grad():
            nn.init.orthogonal_(self.visInProj.weight, generator=gen)
            nn.init.zeros_(self.visInProj.bias)
            nn.init.orthogonal_(self.visOutProj.weight, generator=gen)
            nn.init.zeros_(self.visOutProj.bias)
            for param in self.visInProj.parameters():
                param.requires_grad = False
            for param in self.visOutProj.parameters():
                param.requires_grad = False

        self.doubleBlocks = nn.ModuleList(
            [DoubleStreamJointBlock(self.hiddenDim, numHeads, headDim, i) for i in range(numBlocks)]
        )
        self.ropeCache: Dict[Tuple[int, int, int, str], Tuple[torch.Tensor, torch.Tensor]] = {}

    def buildTimestepEmbedding(self, tVal: float, batchSize: int, device: torch.device, dtype: torch.dtype) -> torch.Tensor:
        halfDim = self.hiddenDim // 2
        freqs = torch.exp(
            -math.log(10000.0) * torch.arange(0, halfDim, device=device, dtype=torch.float32) / float(halfDim)
        )
        args = float(tVal) * 1000.0 * freqs
        emb = torch.cat([torch.cos(args), torch.sin(args)], dim=-1).unsqueeze(0).expand(batchSize, -1)
        return emb.to(dtype)

    def getRopeEmbeddings(
        self,
        txtLen: int,
        gridH: int,
        gridW: int,
        device: torch.device,
        dtype: torch.dtype,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        key = (txtLen, gridH, gridW, str(device))
        if key not in self.ropeCache:
            visLen = gridH * gridW
            totalLen = txtLen + visLen * 2  # [p; c_t; x]
            pos = torch.arange(totalLen, device=device, dtype=torch.float32).unsqueeze(1)
            # Offset reference tokens x by spatial stride so QK^T distinguishes canvas vs reference positions
            pos[txtLen + visLen:] += float(visLen)
            dimIndices = torch.arange(0, self.headDim, 2, device=device, dtype=torch.float32)
            invFreq = 1.0 / (10000.0 ** (dimIndices / float(self.headDim)))
            angles = pos * invFreq.unsqueeze(0)
            anglesFull = torch.cat([angles, angles], dim=-1).unsqueeze(0).unsqueeze(0)
            self.ropeCache[key] = (torch.cos(anglesFull), torch.sin(anglesFull))
        cosTensor, sinTensor = self.ropeCache[key]
        return cosTensor.to(dtype), sinTensor.to(dtype)

    def patchifyLatents(self, latentTensor: torch.Tensor) -> Tuple[torch.Tensor, int, int]:
        # latentTensor: [B, C, H_lat, W_lat] -> [B, N_vis, C * 4]
        bsz, channels, hLat, wLat = latentTensor.shape
        ps = self.patchSize
        padH = (ps - (hLat % ps)) % ps
        padW = (ps - (wLat % ps)) % ps
        if padH > 0 or padW > 0:
            latentTensor = F.pad(latentTensor, (0, padW, 0, padH), mode="reflect")
            _, _, hLat, wLat = latentTensor.shape
        gridH, gridW = hLat // ps, wLat // ps
        patches = latentTensor.view(bsz, channels, gridH, ps, gridW, ps)
        patches = patches.permute(0, 2, 4, 1, 3, 5).reshape(bsz, gridH * gridW, channels * ps * ps)
        return self.visInProj(patches), gridH, gridW

    def runTrajectoryAndComputeVetoObjective(
        self,
        refLatentMean: torch.Tensor,
        params: VetoParameters,
        stepIndex: int,
    ) -> torch.Tensor:
        """
        Executes the 10-step FlowMatchEulerDiscreteScheduler trajectory (Appendix A.1 & B.2):
        - Initializes canvas c_1 ~ N(0, 1) with deterministic seed per PGD step for reproducibility (Appendix B.4).
        - Evaluates hooked double-stream blocks (Block 0 for FLUX.2, Blocks 0..7 for FIBO-EDIT).
        - Computes bidirectional entropy L_VETO = E_{t,l,h}[H(A_{t,l,h}^{c->x}) + H(A_{t,l,h}^{x->c})].
        """
        device = refLatentMean.device
        dtype = refLatentMean.dtype
        bsz = refLatentMean.shape[0]

        # Downsample latent grid if large so 10-step trajectory runs within <1.2 GB VRAM on 6GB GPUs
        _, _, hLat, wLat = refLatentMean.shape
        maxLatSide = 32
        if max(hLat, wLat) > maxLatSide:
            scale = maxLatSide / float(max(hLat, wLat))
            targetH = max(4, int(round(hLat * scale / 2.0)) * 2)
            targetW = max(4, int(round(wLat * scale / 2.0)) * 2)
            refLatentProc = F.interpolate(refLatentMean, size=(targetH, targetW), mode="bilinear", align_corners=False)
        else:
            refLatentProc = refLatentMean

        refTokens, gridH, gridW = self.patchifyLatents(refLatentProc)
        canvasLen = refTokens.shape[1]
        refLen = refTokens.shape[1]

        txtTokens = self.emptyPromptTokens.to(device=device, dtype=dtype).expand(bsz, -1, -1)
        txtLen = txtTokens.shape[1]
        ropeCos, ropeSin = self.getRopeEmbeddings(txtLen, gridH, gridW, device, dtype)

        # Initialize evolving canvas tokens c_t ~ N(0, 1) (Appendix A.1 & B.4 fixed seed reproducibility)
        noiseGen = torch.Generator(device=device).manual_seed(42 + (stepIndex % 5))
        canvasLatent = torch.randn(refLatentProc.shape, generator=noiseGen, device=device, dtype=dtype)
        canvasTokens, _, _ = self.patchifyLatents(canvasLatent)

        hookedIndices = params.hookedBlockIndices
        maxBlockNeeded = max(hookedIndices)

        # FlowMatchEulerDiscreteScheduler timesteps t in [1.0 -> 0.1] over inferenceSteps (default 10)
        numInfer = max(1, params.inferenceSteps)
        timesteps = torch.linspace(1.0, 0.1, steps=numInfer, device=device)
        dt = 1.0 / float(numInfer)

        accumulatedEntropies: List[torch.Tensor] = []

        for tIdx in range(numInfer):
            tVal = float(timesteps[tIdx].item())
            timeEmb = self.buildTimestepEmbedding(tVal, bsz, device, dtype)

            curTxt = txtTokens
            curVisCond = torch.cat([canvasTokens, refTokens], dim=1)

            for bIdx in range(maxBlockNeeded + 1):
                block = self.doubleBlocks[bIdx]
                curTxt, curVisCond, attnProbs = block(curTxt, curVisCond, timeEmb, ropeCos, ropeSin)

                if bIdx in hookedIndices:
                    blockEntropy = computeBidirectionalVetoObjective(
                        fullAttnProbs=attnProbs,
                        textLen=txtLen,
                        canvasLen=canvasLen,
                        refLen=refLen,
                        interactionMode=params.interactionMode,
                        stabilityTau=params.stabilityTau,
                    )
                    accumulatedEntropies.append(blockEntropy)

            # Advance canvas along Euler flow velocity v_t with CFG scale eta = 4.0 (Eq. 3 & Appendix B.2)
            if tIdx < numInfer - 1 and maxBlockNeeded > 0:
                vCond = curVisCond[:, :canvasLen, :]
                with torch.no_grad():
                    zeroRef = torch.zeros_like(refTokens)
                    _, curVisUncond, _ = self.doubleBlocks[0](
                        txtTokens, torch.cat([canvasTokens.detach(), zeroRef], dim=1), timeEmb, ropeCos, ropeSin
                    )
                    vUncond = curVisUncond[:, :canvasLen, :]
                vGuided = vUncond + params.guidanceScale * (vCond - vUncond)
                canvasTokens = canvasTokens - dt * vGuided

        return torch.stack(accumulatedEntropies).mean()


def runNativeDiffusersMmditTrajectory(
    mmditPipeline: object,
    xPerturbed: torch.Tensor,
    params: VetoParameters,
    stepIndex: int,
) -> torch.Tensor:
    """
    Executes VETO on a native HuggingFace Diffusers MMDiT pipeline (FLUX.2 / FIBO-EDIT / FLUX.1 Kontext)
    when loaded in ctx['mmditPipeline'], intercepting the configured double-stream blocks and stopping
    early after the last hooked block to avoid traversing unhooked single-stream blocks.
    """
    transformer = getattr(mmditPipeline, "transformer", None)
    vae = getattr(mmditPipeline, "vae", None)
    if transformer is None or vae is None:
        raise ValueError("mmditPipeline must expose .transformer and .vae modules.")

    device = xPerturbed.device
    dtype = next(transformer.parameters()).dtype

    # 1. Encode reference image x = E_img(x + delta)
    refPosterior = vae.encode(xPerturbed.to(dtype)).latent_dist
    refLatents = refPosterior.mean

    bsz, channels, hLat, wLat = refLatents.shape
    canvasSeqLen = (hLat // 2) * (wLat // 2)
    refSeqLen = canvasSeqLen
    txtSeqLen = params.numTextTokens

    hookMgr = MmditJointAttentionHookManager(
        textLen=txtSeqLen,
        canvasLen=canvasSeqLen,
        refLen=refSeqLen,
        interactionMode=params.interactionMode,
        stabilityTau=params.stabilityTau,
        earlyStopAfterLastBlock=True,
    )
    hookMgr.attachToDiffusersTransformer(
        transformerModel=transformer,
        blockIndices=params.hookedBlockIndices,
        hookStage=params.hookStage,
    )

    try:
        hookMgr.resetStepAccumulator()
        # Run short trajectory through hooked block(s)
        for tStep in range(params.inferenceSteps):
            try:
                # Invoke transformer forward; EarlyBlockStopException halts right after last hooked block
                dummyTxt = torch.zeros((bsz, txtSeqLen, transformer.config.joint_attention_dim), device=device, dtype=dtype)
                packedRef = refLatents.view(bsz, channels, -1).transpose(1, 2)
                packedCanvas = torch.randn_like(packedRef)
                visStream = torch.cat([packedCanvas, packedRef], dim=1)
                tTensor = torch.tensor([1.0 - (tStep / float(max(1, params.inferenceSteps)))], device=device, dtype=dtype)
                transformer(hidden_states=visStream, encoder_hidden_states=dummyTxt, timestep=tTensor)
            except EarlyBlockStopException:
                pass
        return hookMgr.getMeanObjective()
    finally:
        hookMgr.removeHooks()


def executeStandaloneMiFgsm(
    cleanImage01: torch.Tensor,
    vaeEncoder: nn.Module,
    params: Optional[VetoParameters] = None,
    mmditPipeline: Optional[object] = None,
) -> Tuple[torch.Tensor, torch.Tensor, Dict[str, float]]:
    """
    Standalone implementation of Appendix B.2 Equations (7), (8), and (9):
        m^{(k+1)} = tau * m^{(k)} + grad_delta L_VETO / ||grad_delta L_VETO||_1
        delta^{(k+1)} = Proj_{||delta||_inf <= eps}( delta^{(k)} + alpha * sign(m^{(k+1)}) )
    Followed by 8-bit rounding and L-infinity bound verification (Spec Section 0).
    cleanImage01: [1, 3, H, W] float tensor in [0, 1].
    """
    cfg = params or VetoParameters()
    device = cleanImage01.device
    dtype = next(vaeEncoder.parameters()).dtype

    eps01 = cfg.epsilon255 / 255.0
    alpha01 = cfg.stepSize255 / 255.0

    xClean = cleanImage01.detach().clone().float()
    delta = torch.zeros_like(xClean, dtype=torch.float32, requires_grad=True)
    momentumVec = torch.zeros_like(xClean, dtype=torch.float32)

    localSurrogate = LocalDoubleStreamMmditSurrogate(
        latentChannels=4,
        numBlocks=max(cfg.hookedBlockIndices) + 1,
        numHeads=cfg.numHeads,
        headDim=cfg.headDim,
    ).to(device=device, dtype=torch.float32)

    lossTrace: List[float] = []

    for step in range(1, cfg.optimizationSteps + 1):
        if delta.grad is not None:
            delta.grad.zero_()

        xCloaked01 = torch.clamp(xClean + delta, 0.0, 1.0)
        xCloakedNorm = xCloaked01 * 2.0 - 1.0
        xAugmented = DifferentiableAugmenter.applyAugmentation(xCloakedNorm, step, cfg.augmentMode)

        if mmditPipeline is not None:
            vetoObj = runNativeDiffusersMmditTrajectory(mmditPipeline, xAugmented, cfg, step)
        else:
            workImg = F.interpolate(
                xAugmented,
                size=(cfg.workingResolution, cfg.workingResolution),
                mode="bilinear",
                align_corners=False,
            )
            posterior = vaeEncoder.encode(workImg.to(dtype)).latent_dist
            vetoObj = localSurrogate.runTrajectoryAndComputeVetoObjective(posterior.mean.float(), cfg, step)

        vetoObj.backward()
        lossTrace.append(float(vetoObj.item()))

        with torch.no_grad():
            grad = delta.grad
            l1Norm = torch.sum(torch.abs(grad), dim=(1, 2, 3), keepdim=True).clamp(min=1e-12)
            # Equation (8): m^{(k+1)} = tau * m^{(k)} + grad / ||grad||_1
            momentumVec.mul_(cfg.momentumDecay).add_(grad / l1Norm)
            # Equation (9): delta^{(k+1)} = Proj_{||delta||_inf <= eps}(delta^{(k)} + alpha * sign(m^{(k+1)}))
            delta.add_(alpha01 * torch.sign(momentumVec))
            delta.clamp_(-eps01, eps01)
            delta.copy_(torch.clamp(xClean + delta, 0.0, 1.0) - xClean)

    # Spec Section 0: 8-bit rounding of protected output and re-check that L-inf bound holds
    with torch.no_grad():
        xProtectedFloat = torch.clamp(xClean + delta.detach(), 0.0, 1.0)
        xRounded8Bit = torch.round(xProtectedFloat * 255.0) / 255.0
        finalDelta = torch.clamp(xRounded8Bit - xClean, -eps01, eps01)
        xFinal = torch.round(torch.clamp(xClean + finalDelta, 0.0, 1.0) * 255.0) / 255.0
        achievedLinf255 = float((torch.abs(xFinal - xClean).max().item()) * 255.0)
        mseVal = float(torch.mean((xFinal - xClean) ** 2).item())
        psnrVal = 10.0 * math.log10(1.0 / max(mseVal, 1e-10))

    report = {
        "initialEntropy": lossTrace[0] if lossTrace else 0.0,
        "finalEntropy": lossTrace[-1] if lossTrace else 0.0,
        "achievedLinf255": achievedLinf255,
        "psnrDb": psnrVal,
    }
    return xFinal, finalDelta, report