# PhotoGuard (`photoguard`)

- **Authors & Venue:** Hadi Salman, Alaeddin Khaddaj, Guillaume Leclerc, Andrew Ilyas, Aleksander Madry (MIT, ICML 2023)
- **Paper URL:** https://arxiv.org/abs/2302.06588
- **Official Repository:** https://github.com/MadryLab/photoguard
- **Algorithm Class:** Class A (Targeted Latent Encoder Attack)
- **Hardware Tier:** `T1` (5 GB VRAM)

## 1. Threat Model & Objective
Defends personal photographs against unauthorized instruction-guided and mask-based diffusion editing by collapsing the VAE encoder posterior toward a featureless gray target latent before the U-Net or DiT denoising trajectory begins.

## 2. Mathematical Formulation
Adapted from `MadryLab/photoguard` (`encoder_attack`):
$$\min_{\|\delta\|_\infty \le \epsilon} \left\| E_{\mu}(x + \delta) - E_{\mu}(x_{\text{gray}}) \right\|_2^2$$
with published defaults $\epsilon = 16/255$ and $N = 200$ steps.

## 3. Native-Resolution Execution Contract
The perturbation latent is maintained at the full native `(H, W)` image resolution modulated by Lumiya's perceptual visibility map, while editor working-resolution anchors (`0.25 MP` to `4.2 MP`) are evaluated through the differentiable `AutoencoderKL` encoder branch.
