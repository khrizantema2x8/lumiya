# MIRAGE: Policy & Moderation Classifier Alignment Defense

- **Authors / Attribution:** Anshul et al. (*Commercial Multimodal API Refusal Defense*)
- **Primary Defense Target:** Closed-Source Commercial Multimodal APIs (OpenAI GPT-Image, Google Gemini, xAI Grok)
- **Original Paper:** [arXiv Search: MIRAGE Adversarial Protection](https://arxiv.org/search/?query=MIRAGE+adversarial+image+protection&searchtype=all)
- **Module Entrypoint:** `algos/mirage/algo.py`

---

## 1. Threat Model & Problem Formulation

Closed-source commercial image editors preprocess uploaded photographs through vision-language safety and policy moderation classifiers prior to invoking latent generation. Rather than solely attacking the downstream diffusion generator, MIRAGE crafts an imperceptible perturbation that aligns the image's feature projection with moderation boundary anchors, triggering pre-generation safety refusal in commercial APIs.

## 2. Mathematical Formulation

$$
\mathcal{L}_{\text{MIRAGE}}(\delta) = \gamma_{\text{prompt}} \left\| \mu_{\mathcal{E}}\big(\Psi_s(x + \delta)\big) - \mu_{\text{refusal}} \right\|_2^2 + 0.35 \left\| \left|\mathcal{F}\big(\mu_{\mathcal{E}}(\Psi_s(x + \delta))\big)\right| - \left|\mathcal{F}(\mu_{\text{refusal}})\right| \right\|_2^2
$$

- **Multi-Scale Resampling Operator ($\Psi_s$):** Blends native resolution with downsampled-upsampled projections at scale $s = a_{\min}$ so alignment survives API input resizing.
- **Spectral & Latent Anchor Matching:** Aligns both spatial latent coordinates and 2D real FFT magnitudes $|\mathcal{F}(\cdot)|$ with the refusal anchor.

## 3. Implementation in PORTtralica Lumiya

- **Forward Pass (`transformInput`):** Applies differentiable bilinear scale mixing controlled by `ctx["geoAnchorLow"]`.
- **Loss Objective (`computeLoss`):** Weighs latent MSE by `ctx["promptBias"]` (from **Guidance Prompts**) plus orthonormal 2D FFT magnitude distance against `ctx["fftTargetMean"]`.

## 4. Official BibTeX Citation

```bibtex
@article{anshul2025mirage,
  title={MIRAGE: Pre-Generation Moderation Alignment Against Unauthorized Commercial Image Editing},
  author={Anshul and others},
  journal={arXiv preprint},
  year={2025}
}
```
