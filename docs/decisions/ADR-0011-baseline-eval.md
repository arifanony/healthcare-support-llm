# ADR-0011 — Baseline and evaluation methodology

**Status:** proposed (pending human approval) · **Date:** 2026-09-29 · **Stage:** T1

## Context

The experiment's claim ("fine-tuning changed behavior") rests entirely on
comparing two locked evaluations on one frozen golden set at small-n (~100–200).

## Problem

What methodology makes that comparison honest, given one grader, one seed,
and no validated automatic judge?

## Decision

- **Frozen-everything comparison:** golden bytes, harness, decoding config,
  and rubric frozen before the baseline run and reused identically; decoding
  equality verified by script, golden hash checked against the lock at eval time.
- **Human grading as primary signal** on action correctness, relevance,
  safety, unsupported-claim presence, clarification quality, and tone —
  with the full per-example grading sheet published alongside aggregates.
- **Scripted checks auxiliary:** train-text regurgitation (n-gram overlap);
  BLEU/ROUGE-style overlap at most as auxiliary numbers, never as success
  signals. No LLM-as-judge in v1.
- **Honest small-n reporting:** raw counts + paired comparison (McNemar or
  paired bootstrap); "no detectable difference" is a reportable outcome;
  safety-critical slices reported separately, never averaged away.
- **Baseline locked first:** base-model outputs + grades recorded with hashes
  before any fine-tuning result exists.

## Alternatives considered

- **LLM-as-judge primary:** unvalidated judge + small-n = noise with decimal
  points; a validated judge is a project of its own. Deferred to an iteration.
- **Overlap metrics (BLEU/ROUGE) as primary:** correlate poorly with the
  conversational behaviors under test; would optimize wording over action.
  Rejected as primary, kept as auxiliary.
- **Train-loss / val-loss as success:** measures fitting, not behavior; val
  loss drives checkpoint selection only. Rejected as an outcome metric.

## Consequences

- (+) The comparison is defensible and fully auditable (grading sheet + hashes).
- (+) Single-grader consistency without false precision; limitations stated upfront.
- (−) Human grading of ~150×2 outputs is real work — accepted as the cost of signal.
- (−) Low statistical power by design; fine differences are undetectable and
  reported as such.

## Validation

Methodology stands for v1; T12 may propose a validated judge or larger golden
set as the iteration, but may not revise already-locked T11 grades.
