# MetaCloak: Meta-Learning Transformation-Robust Subject Immunization

- **Authors / Attribution:** Yixin Liu, Chenrui Fan, Yutong Dai, Xun Chen, Pan Zhou, Lichao Sun (*CVPR 2024*)
- **Primary Defense Target:** DreamBooth, LoRA & Textual Inversion Subject Personalization under Image Transformations
- **Original Paper:** [arXiv:2311.13127](https://arxiv.org/abs/2311.13127)
- **Module Entrypoint:** `algos/metacloak/algo.py`

---

## 1. Threat Model & Problem Formulation

Unauthorized subject-driven synthesis (DreamBooth and LoRA fine-tuning) needs only 3–5 photographs of a person or artwork to clone their identity. While standard PGD cloaks disrupt clean training pipelines, they are easily defeated by simple preprocessing transformations $\mathcal{T}$ such as Gaussian smoothing, JPEG re-encoding, and spatial cropping.

MetaCloak formulates perturbation crafting as a meta-learning expectation over a pool of surrogate states and differentiable image transformations $\mathcal{T}$ so the resulting cloak survives real-world data-cleaning pipelines.

## 2. Mathematical Formulation

$$
\mathcal{L}_{\text{MetaCloak}}(\delta) = \mathbb{E}_{t \sim \mathcal{T}} \left[ \left\| \mu_{\mathcal{E}}\big(t(x + \delta)\big) - \mu_{\text{target}} \right\|_2^2 + 0.30 \left\| \sigma_{\mathcal{E}}\big(t(x + \delta)\big) - \sigma_{\text{target}} \right\|_2^2 \right]
$$

- **Transformation Pool ($\mathcal{T}$):** Cycles across Gaussian low-pass filtering, Straight-Through Estimator (STE) bit-depth quantization, and multi-scale bilinear resampling.
- **Surrogate Variance Penalty:** Destabilizes latent posterior variance across all transformation branches.

## 3. Implementation in PORTtralica Lumiya

- **Forward Pass (`transformInput`):** Rotates deterministically through three differentiable transformation branches (`Gaussian + STE`, `0.85x bilinear resample`, and `coarse 6-bit STE quantization`) across PGD steps.
- **Loss Objective (`computeLoss`):** Jointly attacks latent posterior mean and standard deviation.

## 4. Official BibTeX Citation

```bibtex
@inproceedings{liu2024metacloak,
  title={MetaCloak: Preventing Unauthorized Subject-Driven Text-to-Image Diffusion-Based Synthesis via Meta-Learning},
  author={Liu, Yixin and Fan, Chenrui and Dai, Yutong and Chen, Xun and Zhou, Pan and Sun, Lichao},
  booktitle={Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)},
  year={2024}
}
```
