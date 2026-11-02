# DiffusionGuard: Early-Timestep & Contour Mask Augmentation Defense

- **Authors / Attribution:** William June Suk Choi et al. (*ICLR 2025*)
- **Primary Defense Target:** Diffusion-Based Inpainting & Brush-Masked Instruction Editors
- **Original Paper:** [arXiv:2410.05694](https://arxiv.org/abs/2410.05694)
- **Module Entrypoint:** `algos/diffusionguard/algo.py`

---

## 1. Threat Model & Problem Formulation

Diffusion inpainting pipelines exhibit high sensitivity during the earliest reverse-diffusion timesteps where global layout and mask-boundary continuity are established. However, perturbations optimized for a fixed mask fail when an attacker draws a slightly larger, smaller, or smoother mask contour.

DiffusionGuard maximizes early-timestep latent reconstruction error under stochastic contour-based mask augmentation (controlling contour strength, shrink iterations, and boundary smoothness) so the protective cloak generalizes across unseen user brush shapes.

## 2. Mathematical Formulation

$$
\mathcal{L}_{\text{DiffusionGuard}}(\delta) = \mathbb{E}_{M \sim \mathcal{M}_{\text{contour}}} \left[ \left\| \mu_{\mathcal{E}}\big((x + \delta) \odot M\big) - \mu_{\text{target}} \right\|_2^2 + 0.35 \left\| \sigma_{\mathcal{E}}\big((x + \delta) \odot M\big) - \sigma_{\text{target}} \right\|_2^2 \right]
$$

- **Contour Mask Distribution ($\mathcal{M}_{\text{contour}}$):** Generates smooth, attenuated boundary bands around shifting mask contours.
- **Posterior Distribution Shift:** Simultaneously disrupts latent mean $\mu_{\mathcal{E}}$ and standard deviation $\sigma_{\mathcal{E}}$.

## 3. Implementation in PORTtralica Lumiya

- **Forward Pass (`transformInput`):** Synthesizes a smooth contour-ring mask scaled by the user's **Mask Augmentation Factor** (`ctx["maskAugFactor"]`).
- **Loss Objective (`computeLoss`):** Minimizes weighted posterior mean and standard deviation MSE against `ctx["zTargetMean"]` and `ctx["zTargetStd"]`.

## 4. Official BibTeX Citation

```bibtex
@inproceedings{choi2025diffusionguard,
  title={DiffusionGuard: A Robust Defense Against Malicious Diffusion-based Image Editing},
  author={Choi, William June Suk and others},
  booktitle={International Conference on Learning Representations (ICLR)},
  year={2025}
}
```
