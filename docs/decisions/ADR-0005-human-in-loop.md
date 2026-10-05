# ADR-0005 — Human-in-the-loop curation

**Status:** proposed (pending human approval) · **Date:** 2026-09-29 · **Stage:** T1

## Context

Automated triage (T5) can grade at scale but cannot be trusted: the triage
model shares the failure modes (overconfidence, missed red flags) of the data
it judges.

## Problem

Where must human judgment be mandatory, and where is automation sufficient?

## Decision

**Triage proposes, the human disposes.** No record enters the curated store
without a named human decision (approve/correct/reject + timestamp,
schema-enforced). The human is likewise final on golden membership (T9) and
result acceptance (T11/T12). Review tooling in v1 is minimal: JSONL
export/import scripts + any editor — no bespoke UI.

## Alternatives considered

- **Full automation (accept triage ACCEPTs sight unseen):** fastest, but bakes
  the triage model's blind spots into training data — the exact failure the
  curation pipeline exists to prevent. Rejected.
- **Full human review of everything including raw:** most rigorous, but at
  ~2–6K atomic examples the triage pre-sort earns its keep by ordering the
  queue (REVIEW first). The bar stays the same; the order gets smart.
- **Bespoke review UI now:** better ergonomics, but weeks of tooling for a
  one-shot ~2K queue. Deferred — build it only if a second curation round
  justifies the investment.

## Consequences

- (+) Every training example is human-attested; the "approved" label means
  something auditable.
- (+) Minimal tooling keeps v1 momentum on the pipeline, not on apps.
- (−) Reviewer throughput is the schedule bottleneck (risk Q5); scope narrows
  before standards drop if it binds.
- (−) Single reviewer = single point of bias; mitigated by the frozen rubric
  and full decision log, stated as a limitation.
