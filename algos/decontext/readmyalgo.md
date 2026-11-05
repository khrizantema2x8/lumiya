# DeContext (`decontext`)

- **Authors & Venue:** Linghui Shen et al. (Dec 2025)
- **Paper URL:** https://arxiv.org/abs/2512.16625
- **Official Repository:** https://github.com/LinghuiiShen/DeContext
- **Algorithm Class:** Class B (DiT Multimodal Context-to-Target Attention Detachment)
- **Hardware Tier:** `T2` (10 GB VRAM)

## 1. Threat Model & Objective
Diffusion Transformer (DiT) editors (such as Flux.1-Fill) synthesize edited regions by attending to unmasked background context tokens via single-stream and double-stream multimodal attention. DeContext uses **Concentrated Context Detachment (CaD)** in early timesteps ($t \in [980, 1000]$, blocks $0\dots25$) to sever target-to-context attention.

## 2. Mathematical Formulation
Adapted from `LinghuiiShen/DeContext`:
$$\mathcal{L}_{\text{DeContext}} = \sum_{l \in [0, 25]} \left\|\text{Softmax}\left(\frac{Q_{\text{target}}^{(l)} (K_{\text{context}}^{(l)})^\top}{\sqrt{d}}\right)\right\|_F^2$$
with published defaults $\epsilon = 25.5/255$ ($0.1$), step size $\alpha = 1.275/255$, and $N = 800$ steps.

