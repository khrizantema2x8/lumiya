# Anti-Inpainting (`anti_inpainting`)

- **Authors & Venue:** Guo et al. (Aug 2025)
- **Paper URL:** https://arxiv.org/abs/2505.13023
- **Algorithm Class:** Class B (Selection-Based Latent Resampling & Morphological Mask Augmentation)
- **Hardware Tier:** `T2` (8 GB VRAM)

## 1. Threat Model & Objective
Targets mask-based diffusion inpainting where the editor resamples stochastic latents $z_0 \sim \mathcal{N}(\mu_\phi(x), \sigma_\phi^2(x))$ inside a user-drawn mask. Even if the posterior mean $\mu_\phi(x_{\text{adv}})$ is shifted slightly, high posterior variance allows benign-looking samples to fall back inside the clean latent distribution sphere.

## 2. Mathematical Formulation
From Section 3 of `arXiv:2505.13023`:
1. **Morphological Mask Augmentation:** Applies iterative dilation ($n > 0$) and erosion ($n < 0$) across $n \in [-\gamma, \gamma]$ via `max_pool2d`.
2. **Selection-Based Latent Resampling:** Draws $K$ posterior samples and pushes the closest candidate outside radius $\tau \cdot r$ of the benign latent centroid ($\epsilon = 16/255$, $N = 800$ steps).
