# Contributing to PORTtralica Lumiya

Thank you for your interest in contributing to PORTtralica Lumiya.

Lumiya is licensed under the PolyForm Shield License 1.0.0. We welcome collaborative open research, bug reports, and especially community contributions to the defense algorithms catalog located in the `algos/` directory.

---

## Algorithm Contribution Policy (`algos/` Directory)

To maintain scientific integrity, rigor, and reproducibility, all contributions to the `algos/` directory must adhere to the following mandatory standards:

### 1. Peer-Reviewed or Established Academic Preprints
Every contributed algorithm must be directly derived from published scientific literature or an established preprint repository (such as ICML, NeurIPS, CVPR, ICLR, IEEE S&P, USENIX Security, ACM CCS, or arXiv). Proprietary, closed-source, or unverified black-box scripts will not be merged.

### 2. Complete Attribution and Citation
Each new algorithm folder submitted to `algos/<algo_name>/` must contain:
- `algo.py`: Module defining `algoMeta` or `ALGO_META` containing `name`, `attribution`, `shortInfo`, `paperUrl`, and hardware constraints.
- `readmyalgo.md`: Documentation containing:
  - Formal academic paper title.
  - Full author list and institutional affiliation.
  - Conference or preprint citation with link (arXiv / DOI).
  - Exact mathematical description of the adversarial objective (loss function, gradient direction, or transformation).
  - Defense target and threat model.
  - Clear disclosure of any implementation adjustments made relative to the original paper.

### 3. Verification and Clean Separation
- Algorithms must implement the standard Lumiya pluggable signature so they run isolated from the core server engine.
- Avoid introducing heavy global dependencies outside standard PyTorch and torchvision wherever possible.
- Verify basic execution with local test assets before submitting pull requests.

---

## Code of Conduct and Scope

- Core codebase contributions (`protect.py`, `ui.html`, `cleaner.py`, `stego/`) should focus on stability, performance, local privacy, and bug fixes.
- All contributions remain subject to the terms of the PolyForm Shield License 1.0.0.

