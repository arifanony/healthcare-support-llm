# ADR-0007 — Golden dataset isolation

**Status:** proposed (pending human approval) · **Date:** 2026-09-29 · **Stage:** T1

## Context

The experiment's only honest signal is baseline-vs-fine-tuned on data neither
has trained on. Contamination (golden text, or even its conversations,
leaking into train) invalidates the comparison silently.

## Problem

How do we guarantee the golden set stays clean, stable, and training-free?

## Decision

- Golden is a **separate locked store** (`data/golden/` + `GOLDEN_LOCK.json`:
  version, locker, hash, count, criteria) — not a slice of a shared file.
- Splits are allocated at **conversation-group granularity** with exact +
  near-dup resolution *before* allocation, so no conversation contributes to
  two splits.
- An automated **contamination check** (shared `source_id` / `conversation_id` /
  text-hash across sets) gates T9 and re-runs at T11 (lock-hash equality).
- Golden changes only by **explicit re-versioning** (+ human approval + recorded
  re-baseline obligation).

## Alternatives considered

- **Random row split:** trivially leaks related turns across sets at this data
  shape. Rejected.
- **Held-out conversations without locking:** stable until someone "fixes" a
  golden example mid-experiment and quietly moves the goalposts. Rejected —
  the lock file exists to make goalpost moves visible and versioned.
- **Withhold golden from the repo (private):** stronger isolation, but kills
  reproducibility (the experiment can't be re-run by anyone else) and
  complicates the local-first setup. Rejected for a personal research project.

## Consequences

- (+) The comparison result is defensible: same bytes, both passes, verified
  by script rather than claimed by memory.
- (+) Near-dup handling is the only fuzzy part, and it is isolated in one
  configured step (T9) with its method recorded.
- (−) Conversation-group splitting + human golden selection yields approximate
  (not exact) 80/10/10 ratios — accepted; integrity beats round numbers.
