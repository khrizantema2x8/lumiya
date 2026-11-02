# IMPRESS: Imperceptible High-Frequency Reconstruction Resilience Defense

- **Authors / Attribution:** Bochuan Cao, Changjiang Li, Ting Wang, Jinyuan Jia, Bo Li, Jinghui Chen (*NeurIPS 2023*)
- **Primary Defense Target:** Diffusion Purification & Low-Pass Filtering Pipelines
- **Original Paper:** [arXiv:2310.19248](https://arxiv.org/abs/2310.19248)
- **Module Entrypoint:** `algos/impress/algo.py`

---

## 1. Threat Model & Problem Formulation

Purification defenses attempt to strip protective perturbations by projecting the image onto a smooth manifold and measuring reconstruction consistency. IMPRESS couples high-frequency spatial residuals directly to VAE latent reconstruction divergence, ensuring that any attempt to filter out the perturbation severely degrades structural image fidelity.

## 2. Mathematical Formulation

$$
\mathcal{L}_{\text{IMPRESS}}(\delta) = \left\| \mu_{\mathcal{E}}\big(x + \delta + \alpha (I - G_\sigma)*(x + \delta)\big) - \mu_{\text{target}} \right\|_2^2 - 0.25 \left\| (I - \mathcal{A}_{3\times 3})\mu_{\mathcal{E}}(x + \delta) \right\|_2^2
$$

- **Residual Pre-Emphasis:** Boosts structural high-pass bands $(I - G_\sigma)*(x + \delta)$ during forward optimization.
- **Latent High-Frequency Variance:** Maximizes local deviation from $3 \times 3$ average-pooled latent neighborhoods $\mathcal{A}_{3 \times 3}$.

## 3. Implementation in PORTtralica Lumiya

- **Forward Pass (`transformInput`):** Extracts high-frequency residual `xDef - F.conv2d(xDef, blurKernel3)` and injects a $0.30\times$ pre-emphasis boost.
- **Loss Objective (`computeLoss`):** Minimizes target MSE while maximizing local latent high-frequency energy.

## 4. Official BibTeX Citation

```bibtex
@inproceedings{cao2023impress,
  title={IMPRESS: Evaluating the Resilience of Imperceptible Perturbations Against Unauthorized Data Usage in Diffusion-Based Generative AI},
  author={Cao, Bochuan and Li, Changjiang and Wang, Ting and Jia, Jinyuan and Li, Bo and Chen, Jinghui},
  booktitle={Advances in Neural Information Processing Systems (NeurIPS)},
  year={2023}
}
```
