# Mist (`mist`)

- **Authors & Venue:** Chumeng Liang, Xiaoyu Wu, Yang Hua, Jiaru Zhang, Yiming Xue, Tao Song, Zhengui Xue, Ruhui Ma, Haibing Guan (ICML 2023)
- **Paper URL:** https://arxiv.org/abs/2305.12683 (AdvDM: https://arxiv.org/abs/2302.04578)
- **Official Repository:** https://github.com/mist-project/mist
- **Algorithm Class:** Class A/B (Fused Textural + Semantic Diffusion Attack)
- **Hardware Tier:** `T1` (5 GB VRAM)

## 1. Threat Model & Objective
Prevents DreamBooth, LoRA, Textual Inversion, and image-to-image style mimicry by combining a structured periodic textural target (`MIST.png` latent pattern) with semantic latent divergence.

## 2. Mathematical Formulation
Adapted from `mist-project/mist` (`mist_v3.py` fused mode):
$$\mathcal{L}_{\text{Mist}}(x_{\text{adv}}) = \|E_{\mu}(x_{\text{adv}}) - z_{\text{MIST}}\|_2^2 - \alpha \|E_{\mu}(x_{\text{adv}}) - E_{\mu}(x_{\text{orig}})\|_1$$
with published defaults $\epsilon = 16/255$ and $N = 100$ steps.

## 3. Native-Resolution Execution Contract
`computeLoss` constructs the multi-frequency orthogonal phase target $z_{\text{MIST}}$ dynamically at each active latent anchor grid and backpropagates gradients directly into the native `(H, W)` perturbation tensor.

