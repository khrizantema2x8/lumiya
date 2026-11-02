# Mist v2 / AdvDM: Directed Gradient Error & Texture Collapse Defense

- **Authors / Attribution:** Chumeng Liang, Xiaoyu Wu, Yang Hua, Jiaru Zhang, Yiming Xue, Tao Song, Haibing Guan (*ICML 2023*)
- **Primary Defense Target:** LoRA, DreamBooth, Textual Inversion & Image-to-Image Style Mimicry
- **Original Paper:** [arXiv:2302.04578](https://arxiv.org/abs/2302.04578)
- **Module Entrypoint:** `algos/mistv2/algo.py`

---

## 1. Threat Model & Problem Formulation

Generative mimicry pipelines extract both semantic concepts and fine-grained brushstroke or skin textures from training photographs. Mist v2 / AdvDM injects directed gradient errors into the latent representation and score-matching trajectory so that any model trained on or conditioned on the protected asset collapses into chaotic, high-frequency scrambled textures.

## 2. Mathematical Formulation

$$
\mathcal{L}_{\text{Mist}}(\delta) = \gamma_{\text{prompt}} \left\| \mu_{\mathcal{E}}(x + \delta) - \mu_{\text{target}} \right\|_2^2 - 0.22 \Big( \left\|\nabla_x \mu_{\mathcal{E}}(x + \delta)\right\|_1 + \left\|\nabla_y \mu_{\mathcal{E}}(x + \delta)\right\|_1 \Big)
$$

- **Directed Semantic Bias ($\gamma_{\text{prompt}}$):** Scales target alignment using the user's **Guidance Prompts (Instance/Class)** trigger.
- **Latent Total-Variation Maximization:** Maximizes spatial finite-difference gradients $\nabla_x, \nabla_y$ inside the 4-channel latent map to induce structured high-frequency texture chaos during decoding.

## 3. Implementation in PORTtralica Lumiya

- **Forward Pass (`transformInput`):** Passes the perturbed tensor directly to preserve high-frequency latent gradient alignment.
- **Loss Objective (`computeLoss`):** Combines prompt-weighted crash target MSE with negative $L_1$ latent spatial gradient penalties.

## 4. Official BibTeX Citation

```bibtex
@inproceedings{liang2023advdm,
  title={Adversarial Example Does Good: Preventing Painting Imitation from Diffusion Models via Adversarial Examples},
  author={Liang, Chumeng and Wu, Xiaoyu and Hua, Yang and Zhang, Jiaru and Xue, Yiming and Song, Tao and Xue, Zhengui and Ma, Ruhui and Guan, Haibing},
  booktitle={International Conference on Machine Learning (ICML)},
  year={2023}
}
```
