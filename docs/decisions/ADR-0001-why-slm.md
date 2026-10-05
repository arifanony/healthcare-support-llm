# ADR-0001 — SLM objective and scope

**Status:** proposed (pending human approval) · **Date:** 2026-09-29 · **Stage:** T1

## Context

The project needs a base model for a ~2K-example conversational-behavior
experiment on personal hardware plus free-tier cloud GPU.

## Problem

Which model scale maximizes learning-per-euro while keeping the full
lifecycle (baseline → fine-tune → evaluate → iterate) reproducible by one
person?

## Decision

Use a Small Language Model (1–4B parameters, instruction-tuned variant) as the
base model.

## Alternatives considered

- **Large model via API fine-tuning (e.g. GPT-class):** no weight access, no
  reproducibility story, recurring cost, and the curation→training loop — the
  actual learning objective — would be outsourced to a black box. Rejected.
- **Mid-size open model (7–13B):** better raw quality, but full-parameter
  training is out of reach and even LoRA at 7B+ strains free-tier VRAM,
  slowing iteration to days per idea. Rejected for v1; revisit if the loop
  proves out and budget appears.
- **Training from scratch:** absurd at this data scale. Rejected outright.

## Consequences

- (+) Full loop runnable on a free Colab T4; fast iteration; every artifact
  reproducible locally except the GPU step.
- (+) Forces the project to win on *data quality* rather than scale — which
  is the thesis being tested.
- (−) Absolute response quality will trail larger models; success is defined
  as *delta over baseline*, never as parity with frontier systems.
- (−) Small models are more brittle to template/format choices; the eval
  harness must control decoding strictly (see evaluation strategy).

## Validation

Provisional until T10: if no shortlisted SLM fits the available backend, the
shortlist (not the SLM decision) changes first.
