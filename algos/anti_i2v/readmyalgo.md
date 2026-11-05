# ▲ Anti-I2V (`anti_i2v`)

- **Authors & Venue:** Vu et al. (Mar 2026)
- **Paper URL:** https://arxiv.org/abs/2603.24570
- **Algorithm Class:** Class E (Lab Chroma + Low-Frequency DCT Image-to-Video Defense)
- **Hardware Tier:** `T1` (6 GB VRAM)
- **Readiness Status:** `▲ Paper Formula Advisory` — No official repository has been released, and our Algorithmic Audit Worksheet (Section M1) identified 3 mathematical contradictions in the printed Algorithm 1:
  1. Applying the 25% low-pass DCT mask directly to $x + \delta$ destroys 75% of the clean image's frequencies; Lumiya applies the 25% low-frequency mask strictly to the perturbation $\delta$.
  2. The printed Lab $\ell_\infty$ bound $0.05$ on $[-100, 100]$ equals $0.012/255$ (zero-change under 8-bit rounding).
  3. The printed LPIPS term uses a minus sign inside minimization, which maximizes perceptual distortion unless flipped.
