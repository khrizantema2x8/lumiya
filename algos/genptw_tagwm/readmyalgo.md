# GenPTW & TAG-WM: Latent-Space Provenance & Tamper Localization Watermark

- **Authors / Attribution:** Dual Latent Provenance & Tamper Localization (*GenPTW & TAG-WM Architecture*)
- **Primary Defense Target:** Post-Edit Tamper Localization & Cryptographic Latent Provenance Verification
- **Original Paper:** [arXiv Search: Latent Space Watermarking Tamper Localization](https://arxiv.org/search/?query=latent+space+watermarking+tamper+localization+diffusion&searchtype=all)
- **Module Entrypoint:** `algos/genptw_tagwm/algo.py`

---

## 1. Threat Model & Problem Formulation

Conventional pixel-domain watermarks are easily destroyed by localized inpainting or JPEG recompression, and they cannot localize which region of an image was spliced by AI. GenPTW & TAG-WM embed a structured parity carrier $W_{\text{parity}}$ directly inside the VAE latent manifold alongside active PGD disruption, ensuring that any localized generative edit disturbs the latent parity grid.

## 2. Mathematical Formulation

$$
\mathcal{L}_{\text{GenPTW}}(\delta) = 0.60 \left\| \mu_{\mathcal{E}}(x + \delta) - \mu_{\text{target}} \right\|_2^2 + 0.40 \left\| \mu_{\mathcal{E}}(x + \delta) - W_{\text{parity}} \right\|_2^2
$$

- **Latent Parity Carrier ($W_{\text{parity}}$):** Alternating $\pm 0.65$ spatial parity grid embedded across the 4-channel latent tensor.
- **Dual Defense & Localization:** Simultaneously degrades unauthorized generative edits while imprinting a forensic frequency signature visible in the **Inspect** tab's *2D Frequency Residual Map*.

## 3. Implementation in PORTtralica Lumiya

- **Forward Pass (`transformInput`):** Preserves full-resolution spatial-spectral perturbations.
- **Loss Objective (`computeLoss`):** Synthesizes the alternating modulo-2 latent parity grid $W_{\text{parity}}$ and optimizes joint MSE with `ctx["zTargetMean"]`.

## 4. Official BibTeX Citation

```bibtex
@article{genptw2025watermark,
  title={GenPTW and TAG-WM: Joint Latent-Space Immunization and Tamper-Localizing Watermarking},
  author={GenPTW Research Group},
  journal={arXiv preprint},
  year={2025}
}
```
