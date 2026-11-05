# PromptFlare (`promptflare`)

- **Authors & Venue:** Nahohyun Na et al. (SKKU, ACM Multimedia 2025)
- **Paper URL:** https://arxiv.org/abs/2508.16217
- **Official Repository:** https://github.com/NAHOHYUN-SKKU/PromptFlare
- **Algorithm Class:** Class B (Prompt-Agnostic Shared-Token Cross-Attention Defense)
- **Hardware Tier:** `T2` (8 GB VRAM)

## 1. Threat Model & Objective
Text-guided image editing models rely on cross-attention maps between spatial latent tokens and text prompt tokens. Because the defender does not know what text prompt an attacker will type at edit time, PromptFlare exploits the fact that every CLIP/T5 text sequence includes shared special tokens (`<BOS>` and `<PAD>`).

## 2. Mathematical Formulation
Adapted from `NAHOHYUN-SKKU/PromptFlare`:
$$\mathcal{L}_{\text{share}} = \left\|M_{\text{share}} \odot A(x_{\text{adv}})\right\|_2^2 - \lambda \left\|(1 - M_{\text{share}}) \odot A(x_{\text{adv}})\right\|_2^2$$
driving cross-attention sink energy into the non-semantic `<BOS>`/`<PAD>` subspaces ($\epsilon = 16/255$, $N = 100$ steps).
