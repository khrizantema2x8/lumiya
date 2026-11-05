# Vid-Freeze (`vid_freeze`)

- **Authors & Venue:** Chowdhury et al. (Sep 2025)
- **Paper URL:** https://arxiv.org/abs/2509.23279
- **Algorithm Class:** Class E (Image-to-Video Temporal Attention Freezing)
- **Hardware Tier:** `T2` (8 GB VRAM)

## 1. Threat Model & Objective
Defends still photographs against unauthorized Image-to-Video (I2V) animation models (such as Stable Video Diffusion, AnimateDiff, and CogVideoX) by forcing generated video frames to remain frozen on Frame 0 rather than synthesizing fabricated motion.

## 2. Mathematical Formulation
From Section 3 of `arXiv:2509.23279`:
1. **Decoupled Temporal Attention Loss:** Drives the temporal self-attention matrix $A_{\text{temp}} \in \mathbb{R}^{F \times F}$ toward the Frame-0 identity column $T_{:, 0} = 1, T_{:, j > 0} = 0$:
   $$\mathcal{L}_{\text{freeze}} = \|A_{\text{temp}}(x_{\text{adv}}) - T_{\text{frame0}}\|_F^2$$
2. **Coupled Spatio-Temporal Suppression:** Minimizes spatial variance across motion-sensitive latent channels ($\epsilon = 16/255$, $N = 100$ steps).
