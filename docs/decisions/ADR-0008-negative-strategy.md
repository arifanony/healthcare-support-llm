# ADR-0008 — Negative examples strategy

**Status:** proposed (pending human approval) · **Date:** 2026-09-29 · **Stage:** T1

## Context

Curation rejects a large share of raw examples (expected: the thesis is that
raw data is uneven). Those failures are information — about what the model
must *not* do.

## Problem

What do we do with rejected examples: discard them, train on them, or reserve
them?

## Decision

- Rejected examples are **kept** in `data/negative/` with a closed-vocabulary
  reason code, verbatim failing response, provenance, and the corrected
  response when one exists.
- Negatives are **excluded from SFT** — ordinary next-token training has no
  mechanism to learn "don't do this" from a bare bad example.
- Negatives are **reserved for**: eval failure-slices, error analysis (T12),
  and future preference pairs (`chosen` = corrected/approved, `rejected` =
  original) for DPO/ORPO-style tuning — a designed but deferred iteration.

## Alternatives considered

- **Discard rejects:** simplest, but destroys the failure taxonomy the T12
  analysis needs and forecloses preference tuning without re-curation. Rejected.
- **Mix negatives into SFT with a "bad" prefix:** folk practice with weak
  theoretical grounding; risks teaching the model to *produce* the bad text
  fluently. Rejected for v1.
- **Run DPO in v1:** doubles the training/eval surface before SFT has proven
  anything. Deferred — the negative store is the bridge that keeps this cheap
  later.

## Consequences

- (+) v1 stays a clean single-variable SFT experiment; the preference-tuning
  option stays open at near-zero carrying cost (one JSONL + reason codes).
- (+) T12 failure analysis can quantify "errors our negatives already
  predicted" — a strong iteration signal.
- (−) If SFT alone cannot suppress behaviors the negatives capture, that
  lesson waits for the iteration round.
