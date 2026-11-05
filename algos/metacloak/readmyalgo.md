# MetaCloak (`metacloak`)

- **Authors & Venue:** Yixin Liu, Chenrui Fan, Yutong Dai, Xun Chen, Pan Zhou, Lichao Sun (Lehigh University, CVPR 2024)
- **Paper URL:** https://arxiv.org/abs/2311.13127
- **Official Repository:** https://github.com/liuyixin-louis/MetaCloak
- **Algorithm Class:** Class D (Bi-Level Surrogate Ensemble + EOT Transformation-Robust Immunization)
- **Hardware Tier:** `T3` (12 GB VRAM)

## 1. Threat Model & Objective
Standard adversarial perturbations against DreamBooth and LoRA personalization are fragile against simple preprocessing transformations such as Gaussian smoothing, cropping, and JPEG quantization. MetaCloak integrates an Expectation Over Transformation (EOT) differentiable transformation pool with surrogate trajectory divergence.

## 2. Mathematical Formulation
Adapted from `liuyixin-louis/MetaCloak`:
$$\min_{\|\delta\|_\infty \le \epsilon} \mathbb{E}_{T \sim \mathcal{T}_{\text{EOT}}} \left[ \mathcal{L}_{\text{denoise}}(T(x + \delta)) \right]$$
where $\mathcal{T}_{\text{EOT}}$ cycles across differentiable Gaussian blur, random spatial crop-and-resize, and Straight-Through Estimator (STE) quantization ($\epsilon = 11/255$, $N = 120$ steps).
