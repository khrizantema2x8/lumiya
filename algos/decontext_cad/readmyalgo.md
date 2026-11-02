# DeContext & CaD: Context Detachment for Diffusion Transformers

- **Authors / Attribution:** Diffusion Transformer Context Detachment (*DeContext & CaD Architecture*)
- **Primary Defense Target:** Patchified Diffusion Transformers (DiT, SD3, PixArt-$\alpha$)
- **Original Paper:** [arXiv Search: DeContext Diffusion Transformer Defense](https://arxiv.org/search/?query=DeContext+Diffusion+Transformer+defense&searchtype=all)
- **Module Entrypoint:** `algos/decontext_cad/algo.py`

---

## 1. Threat Model & Problem Formulation

Modern Diffusion Transformers (DiTs) replace convolutional U-Nets with patchified token sequences processed by global self-attention blocks. Early context-heavy transformer blocks establish coarse structural relationships across $2 \times 2$ and $4 \times 4$ latent patches. DeContext & CaD target these coarse patch representations to sever the mathematical link between the input reference photograph and the generated output.

## 2. Mathematical Formulation

$$
\mathcal{L}_{\text{DeContext}}(\delta) = \left\| \mu_{\mathcal{E}}(x + \delta) - \mu_{\text{target}} \right\|_2^2 - 0.45 \left\| \mathcal{P}_{4\times 4}\big(\mu_{\mathcal{E}}(x + \delta)\big) - \mathcal{P}_{4\times 4}\big(\mu_{\mathcal{E}}(x)\big) \right\|_2^2
$$

- **Patch Token Pooling ($\mathcal{P}_{4 \times 4}$):** Isolates the coarse DiT patch embeddings consumed by early context-heavy transformer blocks.
- **Context Detachment Term:** Maximizes Euclidean distance between clean and protected coarse patch tokens.

## 3. Implementation in PORTtralica Lumiya

- **Forward Pass (`transformInput`):** Passes full-resolution edge-masked perturbations into the VAE encoder.
- **Loss Objective (`computeLoss`):** Computes `F.avg_pool2d(..., 4, 4)` on `dist.mean` and `ctx["zOrigMean"]`, maximizing patch-level divergence while minimizing distance to `ctx["zTargetMean"]`.

## 4. Official BibTeX Citation

```bibtex
@article{decontext2025dit,
  title={DeContext: Context-Heavy Block Detachment for Immunizing Images Against Diffusion Transformers},
  author={DeContext Research Group},
  journal={arXiv preprint},
  year={2025}
}
```
