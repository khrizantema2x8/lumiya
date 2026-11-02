# Anti-Inpainting: 9-Channel Masked Boundary Context Poisoning

- **Authors / Attribution:** Spatial Occlusion & Context-Ring Conditioning Defense (*PORTtralica Research Synthesis*)
- **Primary Defense Target:** 9-Channel Latent Inpainting U-Nets (SD-Inpaint, SDXL-Inpaint, ControlNet-Inpaint)
- **Original Paper:** [arXiv:2302.06588](https://arxiv.org/abs/2302.06588)
- **Module Entrypoint:** `algos/anti_inpainting/algo.py`

---

## 1. Threat Model & Problem Formulation

Dedicated inpainting architectures modify the first U-Net layer to accept 9 latent channels: 4 noisy latent channels $z_t$, 1 binary brush mask channel $M \in \{0, 1\}$, and 4 encoded unmasked context channels $\mathcal{E}(x \odot (1 - M))$. Painting a mask $M$ over a subject erases any adversarial perturbation located inside the mask interior, allowing the model to reconstruct the region from the surrounding unmasked context ring $(1 - M)$.

Anti-Inpainting applies deterministic sliding-window occlusion masks $M_t$ during PGD optimization so every spatial region of the photograph carries self-contained latent disruption and poisons cross-boundary self-attention around arbitrary brush strokes.

## 2. Mathematical Formulation

$$
\mathcal{L}_{\text{AntiInpaint}}(\delta) = \left\| \mu_{\mathcal{E}}\big((x + \delta) \odot (1 - M_t) - 0.5 M_t\big) - \mu_{\text{target}} \right\|_2^2 + 0.25 \left\| \sigma_{\mathcal{E}}\big(x_{\text{masked}}^{(t)}\big) - \sigma_{\text{target}} \right\|_2^2
$$

- **Sliding Occlusion Mask ($M_t$):** Erases a shifting spatial window at step $t$ scaled by the user's **Mask Augmentation Factor**.
- **Joint Posterior Collapse:** Aligns both the latent posterior mean $\mu_{\mathcal{E}}$ and standard deviation $\sigma_{\mathcal{E}}$ with the crash target distribution.

## 3. Implementation in PORTtralica Lumiya

- **Forward Pass (`transformInput`):** Computes prime-stepped sliding occlusion coordinates `(y0, x0)` scaled by `ctx["maskAugFactor"]` to simulate arbitrary user brush masks.
- **Loss Objective (`computeLoss`):** Jointly minimizes MSE on `dist.mean` against `ctx["zTargetMean"]` and `dist.std` against `ctx["zTargetStd"]`.

## 4. Official BibTeX Citation

```bibtex
@inproceedings{salman2023photoguard_inpaint,
  title={Raising the Cost of Malicious AI-Powered Image Editing},
  author={Salman, Hadi and Khaddaj, Alaa and Leclerc, Guillaume and Ilyas, Andrew and Madry, Aleksander},
  booktitle={International Conference on Machine Learning (ICML)},
  year={2023}
}
```
