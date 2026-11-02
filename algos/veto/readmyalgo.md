# VETO: Unified DiT Reference-to-Canvas Attention Entropy Defense

- **Authors / Attribution:** Jonas et al. (*Unified Diffusion Transformer Defense*)
- **Primary Defense Target:** Unified Diffusion Transformers & MMDiT Editors (FLUX.1-Fill, Stable Diffusion 3)
- **Original Paper:** [arXiv Search: VETO DiT Defense](https://arxiv.org/search/?query=VETO+diffusion+transformer+defense&searchtype=all)
- **Module Entrypoint:** `algos/veto/algo.py`

---

## 1. Threat Model & Problem Formulation

Unified Diffusion Transformers (such as Black Forest Labs FLUX and Multimodal DiTs) concatenate reference image tokens and noisy canvas tokens into a single joint sequence, relying on bidirectional reference-to-canvas and canvas-to-reference self-attention to copy identity and scene structure while applying localized edits.

VETO maximizes the Shannon entropy of spatial token attention distributions while orthogonalizing latent token vectors, diffusing the conditioning signal across the token sequence so unified DiT editors fail to anchor edits onto the source photograph.

## 2. Mathematical Formulation

$$
\mathcal{L}_{\text{VETO}}(\delta) = \left\| \mu_{\mathcal{E}}(x + \delta) - \mu_{\text{target}} \right\|_2^2 + 0.55 \cos\big(\mu_{\mathcal{E}}(x + \delta), \mu_{\mathcal{E}}(x)\big) - 0.18 \, \mathcal{H}\Big(\text{softmax}\big(\mu_{\mathcal{E}}(x + \delta)\big)\Big)
$$

- **Token Attention Entropy ($\mathcal{H}$):** Maximizes $-\sum_i p_i \log p_i$ across normalized spatial latent tokens to prevent attention head concentration.
- **Latent Orthogonalization:** Drives cosine similarity between protected and clean token embeddings toward zero.

## 3. Implementation in PORTtralica Lumiya

- **Forward Pass (`transformInput`):** Preserves full-resolution edge-masked pixel perturbations for direct latent token encoding.
- **Loss Objective (`computeLoss`):** Combines crash-target MSE with flattened cosine similarity minimization and negative Shannon entropy regularization.

## 4. Official BibTeX Citation

```bibtex
@article{jonas2025veto,
  title={VETO: Attention Entropy Maximization for Unified Diffusion Transformer Immunization},
  author={Jonas and others},
  journal={arXiv preprint},
  year={2025}
}
```
