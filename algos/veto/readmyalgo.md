# VETO (`veto`)

- **Authors & Venue:** Jonas Grebe, H. Shakibania, T. Braun, Marcus Rohrbach, Anna Rohrbach (TU Darmstadt & hessian.AI, 2026)
- **Paper URL:** https://arxiv.org/abs/2607.27292
- **Algorithm Class:** Class B (MMDiT Bidirectional Joint-Attention Entropy Maximization)
- **Hardware Tier:** `T3` (8–16 GB VRAM in multi-scale token trajectory mode; 80 GB A100 in full FLUX.2 paper evaluation)

## 1. Threat Model & Objective
Modern Multimodal Diffusion Transformers (MMDiTs such as FLUX.2 and FiboEdit) concatenate prompt tokens $p$, noisy canvas tokens $c_t$, and reference image tokens $x$ into a single joint sequence $Z_t = [p; c_t; x]$ and process them with full self-attention. VETO disrupts reference-guided instruction editing by maximizing the un-renormalized bidirectional block entropy between the canvas and reference sub-blocks.

## 2. Mathematical Formulation
Implements Equations (1), (5), and (6) of `arXiv:2607.27292v1` (Appendix A.2):
$$H\left(A_{t,l,h}^{a \to b}\right) = -\sum_{i \in a} \sum_{j \in b} A_{t,l,h,ij} \log\left(A_{t,l,h,ij} + \tau\right)$$
$$\mathcal{L}_{\text{VETO}} = \mathbb{E}_{t,l,h}\left[ H\left(A_{t,l,h}^{c \to x}\right) + H\left(A_{t,l,h}^{x \to c}\right) \right]$$
evaluated across a 10-step Euler flow trajectory with 2D Rotary Position Embeddings (RoPE) at Pareto-optimal budget $\epsilon = 4/255$ and $N = 100$ steps.
