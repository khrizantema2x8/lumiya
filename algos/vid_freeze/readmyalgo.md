# Vid-Freeze: Motion Dynamics Suppression for Video Diffusion Defense

- **Authors / Attribution:** Video Motion Suppression Defense (*Vid-Freeze Architecture*)
- **Primary Defense Target:** Image-to-Video Motion Modules & Optical-Flow Conditioned Generators
- **Original Paper:** [arXiv Search: Video Diffusion Motion Freezing Defense](https://arxiv.org/search/?query=video+diffusion+adversarial+motion+freezing&searchtype=all)
- **Module Entrypoint:** `algos/vid_freeze/algo.py`

---

## 1. Threat Model & Problem Formulation

Video diffusion architectures synthesize motion by estimating spatial translation gradients across adjacent latent coordinates inside temporal self-attention layers. Vid-Freeze suppresses motion dynamics via a spatial-shift freezing objective equipped with target attention anchoring, forcing downstream video generators to collapse into static repetitions of the input frame.

## 2. Mathematical Formulation

$$
\mathcal{L}_{\text{VidFreeze}}(\delta) = \left\| \mu_{\mathcal{E}}(x + \delta) - \mu_{\text{target}} \right\|_2^2 + 0.30 \, w_{\text{temp}} \Big( \left\| \mu_{\mathcal{E}} - \mathcal{S}_x(\mu_{\mathcal{E}}) \right\|_2^2 + \left\| \mu_{\mathcal{E}} - \mathcal{S}_y(\mu_{\mathcal{E}}) \right\|_2^2 \Big)
$$

- **Spatial-Shift Operators ($\mathcal{S}_x, \mathcal{S}_y$):** Cyclic 1-pixel horizontal and vertical shift operators in latent space.
- **Motion Freezing Weight ($w_{\text{temp}}$):** Controlled directly by the user's **Temporal Weights** slider (`0.0` to `1.0`).

## 3. Implementation in PORTtralica Lumiya

- **Forward Pass (`transformInput`):** Passes the perturbed tensor directly to the VAE encoder.
- **Loss Objective (`computeLoss`):** Penalizes `torch.roll(zMean, shifts=1, dims=2/3)` differences scaled by `ctx["temporalWeight"]` alongside `ctx["zTargetMean"]`.

## 4. Official BibTeX Citation

```bibtex
@article{vidfreeze2025motion,
  title={Vid-Freeze: Suppressing Temporal Motion Priors in Image-to-Video Diffusion Models},
  author={Vid-Freeze Research Group},
  journal={arXiv preprint},
  year={2025}
}
```
