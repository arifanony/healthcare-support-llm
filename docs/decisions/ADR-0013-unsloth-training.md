# ADR-0013 — Unsloth as the training framework

**Status:** approved (human-decided 2026-09-30) · **Date:** 2026-09-30 · **Stage:** T1

## Context

v1 runs single-stage LoRA/QLoRA SFT on a free-tier GPU backend
(Colab T4 first; ADR-0010). The docs named the Transformers + PEFT + TRL
ecosystem without pinning the runner, and §2 of the ML architecture only
requires ecosystem compatibility.

## Problem

Which framework executes the T10 training job — optimizing for speed and
VRAM headroom on a free T4?

## Decision

- **Unsloth** executes v1 SFT (LoRA, QLoRA-4bit if the VRAM probe requires
  it), driven by the declarative training job spec, which pins the exact
  `unsloth` version.
- LoRA math stays PEFT-compatible; the run artifact is unchanged (adapter +
  base-model-id + job spec).
- **Fallback:** vanilla TRL SFTTrainer + PEFT if the chosen base model
  lacks Unsloth support — decided at the T10 probe, recorded in the job spec.

## Alternatives considered

- **Vanilla TRL + PEFT as primary:** works everywhere, but slower and
  hungrier for VRAM on a free T4. Kept as the fallback, not the primary.
- **Axolotl:** heavier config surface than one SFT run needs. Rejected for v1.
- **Hand-rolled torch loop:** owns bugs the frameworks already fixed.
  Rejected.

## Consequences

- (+) Faster training and more VRAM headroom on free-tier GPUs.
- (+) Job-spec pin keeps the run reproducible (NFR-4).
- (+) Local env unaffected — `unsloth` is GPU-backend-only, like the
  rest of the ML stack.
- (−) One more backend dependency to pin; support varies by base model —
  the T10 probe gates this, with TRL as the escape hatch.

## Validation

The T10 VRAM probe runs under Unsloth on the actual backend; if the
base-model pick is unsupported, the job spec records the TRL fallback
and this decision is revisited, not silently violated.
