# BlurGuard: Frequency-Naturalness Hardening Against Adversarial Purification

- **Authors / Attribution:** Jongheon Jeong et al. (*Korea University / TAIL Lab, 2025*)
- **Primary Defense Target:** Spatial Low-Pass Filtering, Gaussian Blur & Lossy Quantization Pre-Processing
- **Original Paper:** [arXiv:2511.00143](https://arxiv.org/abs/2511.00143)
- **Module Entrypoint:** `algos/blurguard/algo.py`

---

## 1. Threat Model & Problem Formulation

Standard $L_\infty$-constrained adversarial perturbations concentrate energy in ultra-high spatial frequencies, deviating sharply from the natural $1/f^2$ power spectral density of real photographs. Simple pre-processing filters—such as a $3 \times 3$ Gaussian blur, bilateral filtering, or JPEG quantization—strip away up to 61.5% of baseline protection.

BlurGuard enforces frequency-spectrum naturalness by embedding differentiable Gaussian low-pass filtering $G_\sigma$ and Straight-Through Estimator (STE) quantization $Q$ directly inside the PGD optimization loop, forcing protective perturbations into mid-frequency structural edges that cannot be blurred away without destroying the underlying photograph.

## 2. Mathematical Formulation

$$
\mathcal{L}_{\text{BlurGuard}}(\delta) = \mathbb{E}_{\sigma, Q} \left[ \left\| \mu_{\mathcal{E}}\Big( Q\big( G_{\sigma} * (x + \delta) \big) \Big) - \mu_{\text{target}} \right\|_2^2 \right] + \lambda_{\text{TV}} \, \text{TV}(\delta)
$$

- **Differentiable Low-Pass Convolution ($G_\sigma$):** Attenuates fragile high-frequency gradients during backpropagation ($k = 3, \sigma = 0.85$).
- **STE Quantization ($Q$):** Simulates 8-bit integer rounding and lossy re-encoding with identity gradient pass-through.

## 3. Implementation in PORTtralica Lumiya

- **Forward Pass (`transformInput`):** Convolves `xDef` with the grouped depthwise $3 \times 3$ Gaussian kernel `ctx["blurKernel3"]` and applies STE quantization `xBlur + (quant - xBlur).detach()`.
- **Loss Objective (`computeLoss`):** Minimizes latent posterior mean MSE against `ctx["zTargetMean"]`.

## 4. Official BibTeX Citation

```bibtex
@article{jeong2025blurguard,
  title={BlurGuard: A Simple Approach for Robustifying Image Protection Against AI-Powered Editing},
  author={Jeong, Jongheon and others},
  journal={arXiv preprint arXiv:2511.00143},
  year={2025}
}
```
