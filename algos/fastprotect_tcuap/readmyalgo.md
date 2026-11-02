# FastProtect & TC-UAP: Universal Adversarial Perturbation Basis Defense

- **Authors / Attribution:** Universal Spatial & Temporal Basis Defense (*FastProtect & TC-UAP Architecture*)
- **Primary Defense Target:** Low-Step Rapid Immunization Against Spatial & Temporal Diffusion Pipelines
- **Original Paper:** [arXiv Search: Universal Adversarial Perturbation Diffusion](https://arxiv.org/search/?query=Universal+Adversarial+Perturbation+Diffusion+Protection&searchtype=all)
- **Module Entrypoint:** `algos/fastprotect_tcuap/algo.py`

---

## 1. Threat Model & Problem Formulation

Standard per-image PGD optimization starts from zero initialization, requiring dozens of iterations to discover effective adversarial directions. FastProtect (spatial) and TC-UAP (Temporally-Consistent Universal Adversarial Perturbation) anchor optimization to an orthogonal harmonic UAP basis $\Phi_{\text{UAP}}$ in latent space, accelerating protective convergence in low-step regimes.

## 2. Mathematical Formulation

$$
\mathcal{L}_{\text{FastProtect}}(\delta) = 0.70 \left\| \mu_{\mathcal{E}}(x + \delta) - \mu_{\text{target}} \right\|_2^2 + 0.30 \left\| \mu_{\mathcal{E}}(x + \delta) - \Phi_{\text{UAP}} \right\|_2^2
$$

- **Harmonic Universal Basis ($\Phi_{\text{UAP}}$):** Orthogonal sinusoidal carrier $\sin(\omega_y y)\cos(\omega_x x)$ matched to the resonant spatial frequencies of the `kl-f8` VAE decoder.
- **Fast-Step Convergence:** Guides early PGD iterations directly into high-curvature encoder directions.

## 3. Implementation in PORTtralica Lumiya

- **Forward Pass (`transformInput`):** Passes the perturbed tensor directly to the VAE encoder.
- **Loss Objective (`computeLoss`):** Synthesizes the orthogonal sinusoidal UAP basis $\Phi_{\text{UAP}}$ on the target device and minimizes weighted MSE alongside `ctx["zTargetMean"]`.

## 4. Official BibTeX Citation

```bibtex
@article{fastprotect2025tcuap,
  title={FastProtect and TC-UAP: Universal Adversarial Perturbation Bases for Rapid Diffusion Immunization},
  author={FastProtect Research Group},
  journal={arXiv preprint},
  year={2025}
}
```
