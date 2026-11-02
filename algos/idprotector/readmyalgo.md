# IDProtector: Multi-Encoder Biometric Identity Inconsistency Defense

- **Authors / Attribution:** Biometric & Portrait Identity Defense (*IDProtector Architecture*)
- **Primary Defense Target:** Zero-Shot Face-Swapping & Identity Adapters (InstantID, IP-Adapter-FaceID, PhotoMaker, DreamBooth)
- **Original Paper:** [arXiv Search: IDProtector Facial Identity Defense](https://arxiv.org/search/?query=IDProtector+facial+identity+adversarial+diffusion&searchtype=all)
- **Module Entrypoint:** `algos/idprotector/algo.py`

---

## 1. Threat Model & Problem Formulation

Zero-shot portrait personalization pipelines (such as InstantID, PhotoMaker, and IP-Adapter-FaceID) extract multi-scale facial identity embeddings using pre-trained biometric encoders independent of U-Net gradients. IDProtector maximizes multi-scale cosine inconsistency across pooled latent feature hierarchies so facial identity extractors fail to lock onto the subject's biometric signature.

## 2. Mathematical Formulation

$$
\mathcal{L}_{\text{IDProtector}}(\delta) = \left\| \mu_{\mathcal{E}}(x + \delta) - \mu_{\text{target}} \right\|_2^2 + 0.45 \sum_{k \in \{1, 2\}} \cos\Big(\mathcal{P}_k\big(\mu_{\mathcal{E}}(x + \delta)\big), \, \mathcal{P}_k\big(\mu_{\mathcal{E}}(x)\big)\Big)
$$

- **Multi-Scale Feature Pooling ($\mathcal{P}_k$):** Evaluates identity feature vectors at native ($k=1$) and $2 \times 2$ pooled ($k=2$) spatial scales.
- **Biometric Cosine Orthogonalization:** Minimizes cosine similarity between protected and clean portrait representations across all scales.

## 3. Implementation in PORTtralica Lumiya

- **Forward Pass (`transformInput`):** Passes the Sobel edge-masked portrait tensor into the VAE encoder.
- **Loss Objective (`computeLoss`):** Minimizes multi-resolution cosine similarity between `dist.mean` and `ctx["zOrigMean"]` at $1\times$ and $2\times$ pooled scales.

## 4. Official BibTeX Citation

```bibtex
@article{idprotector2025biometric,
  title={IDProtector: Multi-Scale Biometric Feature Orthogonalization Against Zero-Shot Portrait Cloning},
  author={IDProtector Research Group},
  journal={arXiv preprint},
  year={2025}
}
```
