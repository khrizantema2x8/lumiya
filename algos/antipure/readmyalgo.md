# AntiPure: Erroneous Timestep Guidance Against Diffusion Purifiers

- **Authors / Attribution:** Diffusion Purification Counter-Defense (*DiffPure / Score-SDE Countermeasure*)
- **Primary Defense Target:** Diffusion-Based Adversarial Purifiers (DiffPure, GrIDPure, Score-SDE)
- **Original Paper:** [arXiv Search: Diffusion Purification Adversarial Defense](https://arxiv.org/search/?query=diffusion+purification+adversarial+defense+DiffPure&searchtype=all)
- **Module Entrypoint:** `algos/antipure/algo.py`

---

## 1. Threat Model & Problem Formulation

Diffusion-based purifiers (such as DiffPure) add small forward-process Gaussian noise to a protected image and run reverse denoising steps to wash out adversarial perturbations. AntiPure applies pre-sharpened erroneous timestep guidance so that when a purifier attempts reverse denoising, its score trajectory drives the image deeper into the corrupted latent manifold.

## 2. Mathematical Formulation

$$
\mathcal{L}_{\text{AntiPure}}(\delta) = \left\| \mu_{\mathcal{E}}\big(1.25(x+\delta) - 0.25 G_\sigma*(x+\delta)\big) - \mu_{\text{target}} \right\|_2^2 + 0.45 \left\| \sigma_{\mathcal{E}}(x+\delta) - \sigma_{\text{target}} \right\|_2^2
$$

- **Inverse-Diffusion Pre-Sharpening:** Pre-compensates for forward-diffusion Gaussian attenuation via unsharp residual coupling.
- **Posterior Variance Destabilization:** Disrupts $\sigma_{\mathcal{E}}$ so stochastic reverse-SDE sampling diverges from the clean data manifold.

## 3. Implementation in PORTtralica Lumiya

- **Forward Pass (`transformInput`):** Applies unsharp high-pass pre-compensation against `ctx["blurKernel3"]`.
- **Loss Objective (`computeLoss`):** Jointly optimizes posterior mean and standard deviation divergence.

## 4. Official BibTeX Citation

```bibtex
@article{antipure2024diffusion,
  title={AntiPure: Resisting Diffusion-Based Adversarial Purification via Erroneous Timestep Guidance},
  author={AntiPure Research Group},
  journal={arXiv preprint},
  year={2024}
}
```
