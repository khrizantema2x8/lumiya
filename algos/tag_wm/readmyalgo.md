# ▲ TAG-WM (`tag_wm`) — In-Generation Only

- **Authors & Venue:** Chen et al. (Jun 2025)
- **Paper URL:** https://arxiv.org/abs/2506.23484
- **Official Repository:** https://github.com/Suchenl/TAG-WM
- **Algorithm Class:** Class F (In-Generation Initial Noise Watermarking)
- **Hardware Tier:** `T2` (8 GB VRAM)
- **Readiness Status:** `▲ In-Generation Scope Lock (`photoCompatible: False`)` — Unbundled from `genptw_tagwm`. Per Section M12 & 9.8 of our Algorithmic Audit Worksheet, TAG-WM embeds tree-ring frequency watermarks into the initial Gaussian noise tensor $z_T$ *before* a diffusion model generates a synthetic image from a prompt. It cannot be applied to an already-existing user photograph and is therefore locked out of photo upload queues.

