# ▲ DiffVax (`diffvax`)

- **Authors & Venue:** Ozden et al. (ICLR 2026)
- **Paper URL:** https://arxiv.org/abs/2411.17957
- **Project Page:** https://DiffVax.github.io
- **Algorithm Class:** Class C (Trained Feed-Forward UNet++ Immunizer Network)
- **Hardware Tier:** `T0` (2 GB VRAM at inference)
- **Readiness Status:** `▲ Weight-Blocked` — DiffVax trains a feed-forward UNet++ network (requiring 22 hours on an NVIDIA A100 per target diffusion editor) to emit adversarial perturbations in a single forward pass without test-time PGD. It is **not** a distilled diffusion surrogate. The module will unlock automatically once the authors publish their pretrained UNet++ weights.
