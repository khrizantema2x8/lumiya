# SRIM (`srim`)

- **Authors & Venue:** Guo et al. (USTC, Oct 2026)
- **Paper URL:** https://arxiv.org/abs/2610.07464
- **Algorithm Class:** Class A (Scale-Robust Latent Encoder Immunization)
- **Hardware Tier:** `T1` (6 GB VRAM)

## 1. Threat Model & Objective
Commercial diffusion editors pre-resize user photos to arbitrary working resolutions (`0.25 MP` to `4.2 MP`) using undisclosed interpolation kernels (`bicubic`, `bilinear`, `area`). Fixed-scale adversarial perturbations collapse under this unknown downsampling/upsampling step. SRIM immunizes the native-resolution image across a geometric scale grid with worst-case anchor prioritization.

## 2. Mathematical Formulation
From Section 3 of `arXiv:2610.07464`:
1. **Dynamic Scale Grid & Jitter:** Geometric anchor ratio $1.4$, continuous jitter $s \sim \mathcal{U}[e^{-0.1}, e^{0.1}]$, and random kernel selection $\mathcal{K} \in \{\text{bicubic}, \text{bilinear}, \text{area}\}$.
2. **Relative Latent Deviation:**
   $$r_k(x_{\text{adv}}) = \frac{\|E(P_k(x_{\text{adv}})) - E(P_k(x_{\text{orig}}))\|_2}{\|E(P_k(x_{\text{orig}}))\|_2}$$
3. **Worst-Case Anchor Weighting:** EMA tracking $r_k \leftarrow (1-\beta) r_k + \beta \hat{r}_k$ ($\beta = 0.3$) with Boltzmann prioritization $P(k) \propto \exp(-r_k / \tau)$ ($\tau = 0.1$), published budget $\epsilon = 4/255$, $N = 200$ steps.
