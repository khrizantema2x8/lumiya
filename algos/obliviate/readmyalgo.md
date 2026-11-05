# ▲ Obliviate (`obliviate`) — Generator-Side Unlearning

- **Authors & Venue:** Shakibania et al. (ECCV 2026)
- **Paper URL:** https://arxiv.org/abs/2606.28643
- **Official Repository:** https://github.com/multimodal-ai-lab/Obliviate
- **Algorithm Class:** Class G (Model-Side Autoregressive Generator Concept Unlearning)
- **Hardware Tier:** `T3` (24+ GB VRAM)
- **Readiness Status:** `▲ Generator-Side Scope Lock (`photoCompatible: False`)` — Per Section 1.2 & M19 of our Algorithmic Audit Worksheet, Obliviate fine-tunes LoRA adapters inside autoregressive image generators (`Liquid`, `Emu3-Gen`, `Janus-Pro`) so the generator forgets a target concept or identity. It modifies model weights rather than user images and is therefore locked out of photo upload queues.
