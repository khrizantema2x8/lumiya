# DiffusionGuard (`diffusionguard`)

- **Authors & Venue:** Choi et al. (KAIST, ICLR 2025)
- **Paper URL:** https://arxiv.org/abs/2410.05694
- **Official Repository:** https://github.com/choi403/DiffusionGuard
- **Algorithm Class:** Class B (Early-Step Inpainting & Mask-Robust Diffusion Defense)
- **Hardware Tier:** `T2` (8 GB VRAM)

## 1. Threat Model & Objective
Defends portrait and subject images against mask-based diffusion inpainting editors where an attacker draws an arbitrary binary mask around the subject. Perturbations trained on a fixed mask fail when the attacker shrinks or expands the mask contour.

## 2. Mathematical Formulation
Adapted from `choi403/DiffusionGuard`:
1. **Contour-Shrinking Mask Augmentation:** Applies a Gaussian-smoothed shrinking contour mask $M_{\sigma, \tau}$ at each iteration so gradients concentrate on boundary-invariant features.
2. **First-Step ($t=T$) Norm Maximization:** Maximizes early denoising trajectory deviation $\|z_{\text{adv}} - z_{\text{orig}}\|_2$ combined with target latent collapse ($\epsilon = 16/255$, $N = 100$ steps).
