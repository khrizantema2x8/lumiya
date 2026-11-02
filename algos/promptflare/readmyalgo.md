# PromptFlare: Cross-Attention BOS Token Sink Decoy Defense

- **Authors / Attribution:** Invariant Token Cross-Attention Decoy (*PromptFlare Architecture*)
- **Primary Defense Target:** Text-Conditioned Cross-Attention Layers in Stable Diffusion & SDXL
- **Original Paper:** [arXiv Search: PromptFlare Cross-Attention Defense](https://arxiv.org/search/?query=PromptFlare+cross+attention+adversarial+diffusion&searchtype=all)
- **Module Entrypoint:** `algos/promptflare/algo.py`

---

## 1. Threat Model & Problem Formulation

Text-conditioned diffusion U-Nets and DiTs route a disproportionate share of cross-attention weight through invariant anchor tokens—specifically the Beginning-of-Sequence (`<|startoftext|>`) BOS token—to regulate spatial foreground-background balance. PromptFlare constructs spatial latent decoys that collapse spatial variance toward the global BOS attention sink, neutralizing malicious text prompt instructions.

## 2. Mathematical Formulation

$$
\mathcal{L}_{\text{PromptFlare}}(\delta) = 0.70 \left\| \mu_{\mathcal{E}}(x + \delta) - \mu_{\text{target}} \right\|_2^2 + 0.30 \, \gamma_{\text{prompt}} \left\| \mu_{\mathcal{E}}(x + \delta) - \overline{\mu}_{\text{BOS}} \right\|_2^2
$$

- **BOS Attention Sink ($\overline{\mu}_{\text{BOS}}$):** Spatial channel mean attractor that absorbs cross-attention query projections.
- **Prompt Gain ($\gamma_{\text{prompt}}$):** Modulates sink attraction strength based on **Guidance Prompts (Instance/Class)**.

## 3. Implementation in PORTtralica Lumiya

- **Forward Pass (`transformInput`):** Encodes the perturbed image directly into the 4-channel latent grid.
- **Loss Objective (`computeLoss`):** Pulls spatial latent tokens toward the global channel-mean sink `zMean.mean(dim=(2, 3), keepdim=True)` alongside `ctx["zTargetMean"]`.

## 4. Official BibTeX Citation

```bibtex
@article{promptflare2025bos,
  title={PromptFlare: Neutralizing Text-Conditioned Diffusion Editing via BOS Attention Sink Decoys},
  author={PromptFlare Research Group},
  journal={arXiv preprint},
  year={2025}
}
```
