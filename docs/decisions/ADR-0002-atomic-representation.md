# ADR-0002 — Atomic decision-point representation

**Status:** proposed (pending human approval) · **Date:** 2026-09-29 · **Stage:** T1

## Context

Raw data arrives as multi-turn conversations of uneven quality; a single
conversation may contain one excellent exchange and three poor ones.

## Problem

Training on whole conversations teaches the model to imitate the average —
including the poor turns. How do we make quality judgments (and training
targets) precise?

## Decision

Decompose conversations into **atomic decision-point examples**: one record per
patient message, carrying the relevant history, a behavioral action label, and
a single target response (schema `atomic/v1`).

## Alternatives considered

- **Whole-conversation SFT:** simplest, but quality labels attach to the whole
  bundle — one bad turn poisons (or one good turn rescues) the entire example.
  Rejected.
- **Multi-turn targets (assistant predicts several turns):** richer signal but
  muddier credit assignment at small-n, and review cost multiplies. Deferred —
  revisit if single-turn SFT plateaus for lack of context modeling.
- **Turn-pair only (no history):** cheapest, but destroys the conversational
  behavior we are trying to teach (clarification depends on history). Rejected.

## Consequences

- (+) Quality, safety, and action labels attach to exactly the behavior they
  judge; review and eval slice cleanly.
- (+) 2K conversations yield more atomic examples (est. 2–6K), improving the
  data budget without new sourcing.
- (−) Extraction rules can mis-slice context; mitigated by the T4 spot-check
  gate (AC-T4-3).
- (−) Splitting must group by conversation to avoid leakage — handled in T9
  (ADR-0007, data-architecture §5).

## Validation

Assumption A5 (atomic trains better) is tested empirically at T11; if SFT shows
no behavior transfer, representation is a prime suspect for the T12 analysis.
