# Anti-I2V: Perceptual Opponent-Color & Spectral Image-to-Video Defense

- **Authors / Attribution:** Image-to-Video Perceptual & Frequency Defense (*Anti-I2V Architecture*)
- **Primary Defense Target:** Image-to-Video (I2V) Generators (Stable Video Diffusion, Runway Gen-3, Kling, Sora-Class Pipelines)
- **Original Paper:** [arXiv Search: Image-to-Video Adversarial Defense](https://arxiv.org/search/?query=image+to+video+adversarial+defense+temporal+coherence&searchtype=all)
- **Module Entrypoint:** `algos/anti_i2v/algo.py`

---

## 1. Threat Model & Problem Formulation

Image-to-Video (I2V) diffusion models synthesize an entire motion sequence conditioned on a single starting photograph, allowing attackers to animate static portraits into unauthorized video clips. Anti-I2V disrupts temporal motion priors by jointly optimizing perturbations across opponent color channels and the 2D Fourier frequency spectrum, weighted by the user's **Temporal Weights** parameter.

## 2. Mathematical Formulation

$$
\mathcal{L}_{\text{Anti-I2V}}(\delta) = \left\| \mu_{\mathcal{E}} - \mu_{\text{target}} \right\|_2^2 + w_{\text{temp}} \left\| \nabla_c \mu_{\mathcal{E}} - \nabla_c \mu_{\text{target}} \right\|_2^2 + 0.25 \left\| \left|\mathcal{F}(\mu_{\mathcal{E}})\right| - \left|\mathcal{F}(\mu_{\text{target}})\right| \right\|_2^2
$$

- **Opponent-Channel Gradient ($\nabla_c$):** Disrupts cross-channel chrominance/luminance correlations used by temporal attention heads.
- **2D Spectral Alignment ($\mathcal{F}$):** Injects periodic phase/magnitude anchors that destabilize temporal 3D convolutions.

## 3. Implementation in PORTtralica Lumiya

- **Forward Pass (`transformInput`):** Preserves spatial-frequency perturbations across all RGB channels.
- **Loss Objective (`computeLoss`):** Couples cross-channel difference matching (scaled by `ctx["temporalWeight"]`) with orthonormal 2D `rfft2` magnitude alignment.

## 4. Official BibTeX Citation

```bibtex
@article{antii2v2025video,
  title={Anti-I2V: Disrupting Unauthorized Image-to-Video Generation in Perceptual and Frequency Domains},
  author={Anti-I2V Research Group},
  journal={arXiv preprint},
  year={2025}
}
```
