# Example Algorithm (`example`)

- **Authors & Venue:** Author et al., Venue Year
- **Paper URL:** https://arxiv.org/abs/0000.00000
- **Official Repository:** https://github.com/org/repo
- **Algorithm Class:** Class A (Latent Encoder / Representation Attack)
- **Hardware Tier:** `T1` (Minimum 6 GB VRAM)

## 1. Threat Model & Objective
Describe the generative editing or customization pipeline this algorithm defends against (e.g., latent diffusion image-to-image, inpainting, LoRA personalization, or image-to-video generation).

## 2. Mathematical Formulation
State the published optimization objective and constraints:
$$\min_{\|\delta\|_\infty \le \epsilon} \mathcal{L}(E(x + \delta), z_{\text{target}})$$

## 3. Native-Resolution Execution Contract
Explain how `transformInput(xDef, step, ctx)` and `computeLoss(dist, ctx)` execute inside Lumiya's native-resolution optimization harness while keeping output perturbations anchored to the original `(H, W)` pixel grid.

