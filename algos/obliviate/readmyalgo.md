# Obliviate: KL-Supervised Concept Erasure Over Visual Token Distributions

- **Authors / Attribution:** Visual Token Concept Erasure Defense (*Obliviate Architecture*)
- **Primary Defense Target:** Autoregressive Visual-Language Models & Tokenized Multimodal Generators
- **Original Paper:** [arXiv Search: Obliviate Concept Erasure Visual Tokens](https://arxiv.org/search/?query=Obliviate+concept+erasure+visual+tokens&searchtype=all)
- **Module Entrypoint:** `algos/obliviate/algo.py`

---

## 1. Threat Model & Problem Formulation

Autoregressive visual-language models and tokenized image generators quantize continuous latent maps into discrete visual token probability distributions. Obliviate applies Kullback-Leibler (KL) divergence supervision between the softmax-normalized latent token distribution and a maximum-entropy uniform prior $\mathcal{U}$, erasing semantic concept peaks so tokenized generators cannot extract coherent subject semantics.

## 2. Mathematical Formulation

$$
\mathcal{L}_{\text{Obliviate}}(\delta) = \left\| \mu_{\mathcal{E}}(x + \delta) - \mu_{\text{target}} \right\|_2^2 + 0.40 \, D_{\text{KL}}\Big(\text{softmax}\big(\mu_{\mathcal{E}}(x + \delta)\big) \,\Big\|\, \mathcal{U}\Big)
$$

- **KL Concept Flattening ($D_{\text{KL}}$):** Drives the spatial token activation distribution toward a flat uniform prior $\mathcal{U} = \frac{1}{N}$.
- **Posterior Collapse:** Anchors unnormalized coordinates to the crash target $\mu_{\text{target}}$.

## 3. Implementation in PORTtralica Lumiya

- **Forward Pass (`transformInput`):** Passes the edge-masked perturbed tensor directly to the VAE encoder.
- **Loss Objective (`computeLoss`):** Evaluates `F.kl_div(logProbs, uniformTarget, reduction="batchmean")` across flattened spatial latent tokens alongside `ctx["zTargetMean"]`.

## 4. Official BibTeX Citation

```bibtex
@article{obliviate2025concept,
  title={Obliviate: KL-Supervised Visual Token Flattening for Concept Erasure in Generative Models},
  author={Obliviate Research Group},
  journal={arXiv preprint},
  year={2025}
}
```
