# IDGuardian (`idguardian`)

- **Authors & Venue:** Xiong et al. (Oct 2026)
- **Paper URL:** https://arxiv.org/abs/2610.19717
- **Official Repository:** https://github.com/OpenAscent-L/IDGuardian
- **Algorithm Class:** Class B (Dual-Encoder Identity Cloaking + Adversarial Conceptual Bridge)
- **Hardware Tier:** `T2` (8 GB VRAM)

## 1. Threat Model & Objective
Zero-shot and tuning-based facial customization pipelines (InstantID, IP-Adapter-FaceID, PhotoMaker, DreamBooth) extract identity embeddings from both facial recognition backbones (FaceNet/ArcFace) and semantic vision encoders (CLIP ViT). IDGuardian jointly disrupts both identity subspaces while driving diffusion score trajectories away from the subject's conceptual bridge.

## 2. Mathematical Formulation
Adapted from Algorithm 1 of `OpenAscent-L/IDGuardian` (`arXiv:2610.19717`):
$$\mathcal{L}_{\text{ID}} = \left(1 - \cos(E_f(x_{\text{adv}}), E_f(x))\right) + \left(1 - \cos(E_c(x_{\text{adv}}), E_c(x))\right)$$
$$\mathcal{L}_{\text{total}} = \mathcal{L}_{\text{ID}} + \lambda_{\text{ACB}} \mathcal{L}_{\text{ACB}}(x_{\text{adv}}, x)$$
with published defaults $\epsilon = 8/255$ and $N = 200$ steps.

