# PhotoGuard (encoder attack)

Salman, Khaddaj, Leclerc, Ilyas, Madry. ICML 2023. https://arxiv.org/abs/2302.06588
Official code: https://github.com/MadryLab/photoguard (MIT licence)

## What it does
Sign-gradient descent moves the Stable Diffusion VAE latent of the photo toward the latent of a gray image, within an L-inf budget.

## Paper defaults
Budget 16/255, 200 steps, step 2/255.

## Lumiya differences
- The paper works at 512x512. Lumiya keeps the layer on the native pixel grid and resizes only inside the attack, cycling 0.25 MP to 0.6 MP working sizes on GPUs under 8 GB.
- The paper's 16/255 sign steps are visible: on a native-size photo they gave 27 dB and a worm texture. Lumiya uses scaled gradients, a soft limit, a texture map that shrinks the layer in flat areas, and dithered rounding.
- The default budget is 4/255, not the paper's 16/255. On a test photo this gave 46 dB and about half the paper setting's latent disruption after 60 steps.
- None of these changes has been validated against the paper's results.

## Limits
Crops, filters, rotation, JPEG and purification can weaken it. It is aimed at Stable Diffusion family editors and transfers weakly to modern DiT editors and closed APIs.
