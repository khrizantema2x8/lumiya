# SRIM: Scale-Robust Image Immunization via Minimax Geometric Anchors

- **Authors / Attribution:** Worst-Case Scale-Robust Minimax Defense (*SRIM Architecture*)
- **Primary Defense Target:** Arbitrary Resizing, Downscaling & Multi-Aspect Scraping Pipelines
- **Original Paper:** [arXiv Search: Scale-Robust Diffusion Defense](https://arxiv.org/search/?query=scale+robust+image+protection+diffusion&searchtype=all)
- **Module Entrypoint:** `algos/srim/algo.py`

---

## 1. Threat Model & Problem Formulation

Automated scraping and editing pipelines routinely resize or downscale input photographs across arbitrary aspect ratios before feeding them into latent encoders, attenuating single-resolution adversarial perturbations. SRIM formulates immunization as a minimax optimization over user-defined **Geometric Anchors** $[a_{\min}, a_{\max}]$ so the perturbation remains lethal across the entire scaling interval.

## 2. Mathematical Formulation

$$
\min_{\|\delta\|_\infty \le \epsilon} \; \max_{a \in [a_{\min}, a_{\max}]} \left\| \mu_{\mathcal{E}}\big(\mathcal{R}_{a}(x + \delta)\big) - \mu_{\text{target}} \right\|_2^2
$$

- **Multi-Scale Resampling ($\mathcal{R}_a$):** Evaluates bicubic downscaling and upscaling across anchor points in $[a_{\min}, a_{\max}]$ (defaulting to $1.7$–$7.1$).
- **Worst-Case Quartile Penalty:** Concentrates gradient updates on the highest-error spatial latent coordinates.

## 3. Implementation in PORTtralica Lumiya

- **Forward Pass (`transformInput`):** Sweeps bicubic resampling scales between `ctx["geoAnchorLow"]` and `ctx["geoAnchorHigh"]`.
- **Loss Objective (`computeLoss`):** Combines global latent MSE with a top-25% worst-case coordinate penalty (`torch.quantile(sqDiff, 0.75)`).

## 4. Official BibTeX Citation

```bibtex
@article{srim2025scalerobust,
  title={SRIM: Scale-Robust Image Immunization Against Arbitrary Resizing in Diffusion Editing},
  author={SRIM Research Group},
  journal={arXiv preprint},
  year={2025}
}
```
