# ChronoLock: Temporal Denoising & Cross-Chunk Boundary Disruption

- **Authors / Attribution:** Long-Horizon Video Chunk Defense (*ChronoLock Architecture*)
- **Primary Defense Target:** Sliding-Window & Multi-Chunk Video Diffusion Pipelines
- **Original Paper:** [arXiv Search: Temporal Chunk Boundary Video Defense](https://arxiv.org/search/?query=temporal+chunk+boundary+adversarial+video+diffusion&searchtype=all)
- **Module Entrypoint:** `algos/chronolock/algo.py`

---

## 1. Threat Model & Problem Formulation

Long-horizon video generation pipelines synthesize clips in overlapping temporal chunks, stitching adjacent chunks via boundary conditioning frames. ChronoLock balances intra-chunk latent collapse with cross-chunk partition discontinuity (controlled by **Temporal Weights**) so temporal coherence breaks down across chunk boundaries.

## 2. Mathematical Formulation

$$
\mathcal{L}_{\text{ChronoLock}}(\delta) = \left\| \mu_{\mathcal{E}}(x + \delta) - \mu_{\text{target}} \right\|_2^2 - 0.35 \, w_{\text{temp}} \left\| \mu_{\mathcal{E}}^{(\text{upper})} - \mu_{\mathcal{E}}^{(\text{lower})} \right\|_2^2
$$

- **Intra-Chunk Collapse:** Drives global latent coordinates toward the static crash target $\mu_{\text{target}}$.
- **Cross-Partition Discontinuity:** Maximizes divergence between upper and lower spatial-temporal latent partitions weighted by $w_{\text{temp}}$.

## 3. Implementation in PORTtralica Lumiya

- **Forward Pass (`transformInput`):** Preserves full-resolution edge-masked pixel perturbations.
- **Loss Objective (`computeLoss`):** Maximizes partition boundary MSE scaled by `ctx["temporalWeight"]` alongside crash target alignment.

## 4. Official BibTeX Citation

```bibtex
@article{chronolock2025temporal,
  title={ChronoLock: Breaking Multi-Chunk Temporal Coherence in Video Diffusion Synthesis},
  author={ChronoLock Research Group},
  journal={arXiv preprint},
  year={2025}
}
```
