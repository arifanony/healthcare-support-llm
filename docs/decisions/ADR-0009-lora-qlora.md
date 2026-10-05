# ADR-0009 — LoRA / QLoRA fine-tuning

**Status:** proposed — method fixed, hyperparameters provisional (pending human approval) · **Date:** 2026-09-29 · **Stage:** T1

## Context

Full-parameter fine-tuning of even a 1–3B model exceeds free-tier GPU memory
once optimizer states are counted, and produces GB-scale checkpoints per run.

## Problem

Which fine-tuning method fits a free Colab T4, keeps artifacts small and
versionable, and still tests the curation thesis?

## Decision

**LoRA** (provisional r=16, α=32), dropping to **QLoRA 4-bit** if VRAM
requires it. Adapters (tens of MB) are the run artifact; base weights are
never modified or stored.

## Alternatives considered

- **Full fine-tuning:** unaffordable on free tier; massive artifacts; higher
  overfitting risk at ~2K examples. Rejected.
- **Prompt-tuning / prefix-tuning:** cheaper still, but weaker behavior-shaping
  evidence for conversational tasks and poorer tooling in the PEFT/TRL
  ecosystem. Rejected for v1.
- **In-context learning only (no training):** zero GPU need, but abandons the
  project's core objective — demonstrating the fine-tuning lifecycle. Rejected.

## Consequences

- (+) Trainable on a T4-16GB; run artifacts are MB-scale and diffable by config.
- (+) Adapter + base-model-id fully describes the model — reproducibility
  without weight storage.
- (−) LoRA capacity may underfit if the behavior shift is large; rank is the
  documented knob (raise to 32/64 in an iteration if T11 shows underfitting).
- (−) QLoRA quantization adds a small quality/VRAM tradeoff decided by the
  T10 VRAM probe, recorded in the job spec.

## Validation

Method stands unless the T10 probe shows even QLoRA-4bit on the smallest
shortlisted model cannot fit — in which case the fallback chain is: smaller
model → gradient accumulation/offload → Kaggle GPU → paid tier (human decides).
