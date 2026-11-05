# BlurGuard (`blurguard`)

- **Authors & Venue:** Kim et al. (KAIST, NeurIPS 2025)
- **Paper URL:** https://arxiv.org/abs/2511.00143
- **Official Repository:** https://github.com/jsu-kim/BlurGuard
- **Algorithm Class:** Class A (Optical Defocus Target + Spectral PSD Regularized Attack)
- **Hardware Tier:** `T1` (6 GB VRAM)

## 1. Threat Model & Objective
Standard encoder attacks shift latents toward unnatural out-of-distribution targets (such as solid gray or checkerboard patterns), which introduce high-frequency spectral spikes vulnerable to low-pass purification. BlurGuard pushes the encoder latent toward a natural optical defocus (Gaussian blur) manifold while constraining the 2D radial Power Spectral Density (PSD) log-ratio.

## 2. Mathematical Formulation
Adapted from `jsu-kim/BlurGuard`:
$$\mathcal{L}_{\text{BlurGuard}}(x_{\text{adv}}) = \left\|E_{\mu}(x_{\text{adv}}) - E_{\mu}(G_{\sigma}(x_{\text{orig}}))\right\|_2^2 + \lambda_{\text{PSD}} \left\|\log_{10} \text{PSD}(x_{\text{adv}}) - \log_{10} \text{PSD}(x_{\text{orig}})\right\|_1$$
with published defaults $\epsilon = 16/255$ and $N = 200$ steps.
