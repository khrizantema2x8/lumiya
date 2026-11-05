# ▲ ChronoLock (`chronolock`)

- **Authors & Venue:** He et al. (Jun 2026)
- **Paper URL:** https://arxiv.org/abs/2606.21146
- **Algorithm Class:** Class D/E (Bi-Level Temporal LoRA Video Customization Defense)
- **Hardware Tier:** `T3` (24+ GB VRAM)
- **Readiness Status:** `▲ Multi-Frame Video & Hardware Blocker` — ChronoLock defends 5-frame video sequences against MotionDirector temporal LoRA customization by alternating inner temporal-LoRA weight updates with outer frame-perturbation steps on 4x NVIDIA RTX A6000 GPUs. It cannot execute on a single still photograph.
