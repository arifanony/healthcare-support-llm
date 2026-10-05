# Training docs

Training strategy lives in [../architecture/ml-architecture.md](../architecture/ml-architecture.md);
remote execution in [../architecture/environment-design.md](../architecture/environment-design.md)
and [../decisions/ADR-0010-colab-gpu-execution.md](../decisions/ADR-0010-colab-gpu-execution.md);
the job-spec contract draft in [../data/data-contract.md](../data/data-contract.md) §9.

This directory will hold:

- `job-spec.md` — finalized job-spec reference (written at T10).
- `runbook-colab.md` — step-by-step backend runbook (written at T10).
- `vram-probe.md` — backend probe results informing the final base-model pick (T10).

Nothing here yet by design: backend specifics are decided at T10, not T1.
