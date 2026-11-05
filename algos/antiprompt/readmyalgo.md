# Anti-Prompt (`antiprompt`)

- **Authors & Venue:** Yeonghwan Song et al. (Jul 2026)
- **Paper URL:** https://arxiv.org/abs/2607.01499
- **Official Repository:** https://github.com/yeonghwansong/Anti-Prompt-code
- **Algorithm Class:** Class E (Image-to-Video Text-Conditioned Cross-Attention Decoupling)
- **Hardware Tier:** `T2` (8 GB VRAM)

## 1. Threat Model & Objective
Image-to-Video (I2V) diffusion models condition video generation simultaneously on an input anchor image and a user-supplied motion text prompt. Anti-Prompt decouples the cross-attention alignment between visual latent queries $Q(E(x_{\text{adv}}))$ and text prompt keys $K(\text{prompt})$ so the generator fails to execute the requested motion trajectory.

## 2. Mathematical Formulation
Adapted from `yeonghwansong/Anti-Prompt-code` (`arXiv:2607.01499v3`):
$$\mathcal{L}_{\text{Anti-Prompt}} = \cos\left(\text{Attn}(Q(x_{\text{adv}}), K_{\text{prompt}}), \text{Attn}(Q(x_{\text{orig}}), K_{\text{prompt}})\right) + \lambda_{\text{enc}} \|E(x_{\text{adv}}) - z_{\text{target}}\|_2^2$$
with published defaults $\epsilon = 16/255$ and $N = 100$ steps.

