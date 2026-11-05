# AntiPure (`antipure`)

- **Authors & Venue:** Yang et al. (ICCV 2025)
- **Paper URL:** https://arxiv.org/abs/2509.13922
- **Algorithm Class:** Class B (Purification-Resilient Diffusion Immunization)
- **Hardware Tier:** `T2` (8 GB VRAM)

## 1. Threat Model & Objective
Adversaries frequently run DiffPure, GridPure, or Gaussian noise purification ($t \in [1, t_p]$) before customization to strip adversarial perturbations. AntiPure embeds perturbations that actively exploit the purifier's denoising trajectory so purification amplifies rather than removes the defense.

## 2. Mathematical Formulation
From `arXiv:2509.13922`:
1. **Patch-wise Frequency Guidance (PFG):** Divides the image into $s \times s$ patches ($s=8$), transforms into the frequency domain, and weights the bottom-right high-frequency quadrant by $\exp(\bar{\alpha}_t - 1)$.
2. **Erroneous Timestep Guidance (ETG):** Aligns purification-window latents ($t \in [1, t_p]$) toward the high-noise erroneous trajectory state $t_{\text{err}} = 999$ ($\epsilon = 16/255$, $N = 100$ steps).
