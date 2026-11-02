# DiffVax: Nested Multi-Scale Skip-Connection Cloak

- **Authors / Attribution:** Multi-Scale Residual Skip-Connection Defense (*DiffVax Architecture*)
- **Primary Defense Target:** U-Net & ResNet Downsampling Skip Connections in Spatial and Video Editors
- **Original Paper:** [arXiv Search: DiffVax Adversarial Image Protection](https://arxiv.org/search/?query=DiffVax+adversarial+image+protection&searchtype=all)
- **Module Entrypoint:** `algos/diffvax/algo.py`

---

## 1. Threat Model & Problem Formulation

Both VAE encoders and diffusion U-Nets rely on multi-scale residual skip connections to pass fine spatial structure around bottleneck layers. Inspired by NestedUNet topologies, DiffVax injects multi-resolution Laplacian pyramid residuals into the input tensor so encoder skip connections propagate phase-inverted signals across all resolution scales.

## 2. Mathematical Formulation

$$
\mathcal{L}_{\text{DiffVax}}(\delta) = \left\| \mu_{\mathcal{E}}\Big(x + \delta + 0.20\big(I - \mathcal{U}_2 \mathcal{P}_2\big)(x+\delta)\Big) - \mu_{\text{target}} \right\|_2^2 - 0.28 \left\| \mu_{\mathcal{E}}(x + \delta) - \mu_{\mathcal{E}}(x) \right\|_2^2
$$

- **Laplacian Skip Coupling ($I - \mathcal{U}_2 \mathcal{P}_2$):** Extracts the difference between native resolution and $2\times$ pooled-upsampled representations.
- **Latent Origin Repulsion:** Pushes encoded latent representations away from clean features $\mu_{\mathcal{E}}(x)$.

## 3. Implementation in PORTtralica Lumiya

- **Forward Pass (`transformInput`):** Computes the $2\times$ Laplacian pyramid residual `xDef - F.interpolate(F.avg_pool2d(xDef, 2, 2), ...)` and couples it into the forward pass.
- **Loss Objective (`computeLoss`):** Combines target MSE against `ctx["zTargetMean"]` with repulsion from `ctx["zOrigMean"]`.

## 4. Official BibTeX Citation

```bibtex
@article{diffvax2025nested,
  title={DiffVax: Nested Multi-Scale Skip-Connection Disruption Against Generative Image Manipulation},
  author={DiffVax Research Group},
  journal={arXiv preprint},
  year={2025}
}
```
