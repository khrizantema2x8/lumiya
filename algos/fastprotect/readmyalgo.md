# ▲ FastProtect (`fastprotect`)

- **Authors & Venue:** Ahn et al. (NAVER WEBTOON AI, CVPR 2025)
- **Paper URL:** https://arxiv.org/abs/2412.11423
- **Project Page:** https://webtoon.github.io/impasto
- **Algorithm Class:** Class C (Amortized Cluster Perturbation Mixture)
- **Hardware Tier:** `T0` (2 GB VRAM)
- **Readiness Status:** `▲ Weight-Blocked` — FastProtect achieves sub-second inference by combining $K=4$ pre-computed K-means++ RGB cluster perturbations with 3 target pattern sets via patch-wise LPIPS weighting. The authors have not publicly released the pre-computed cluster banks.

