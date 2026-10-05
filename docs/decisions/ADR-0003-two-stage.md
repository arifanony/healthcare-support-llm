# ADR-0003 — Action + response decomposition

**Status:** proposed — metadata-only in v1, training use deferred (pending human approval) · **Date:** 2026-09-29 · **Stage:** T1

## Context

Each atomic example carries both *what to do* (action label: answer, clarify,
refuse, …) and *what to say* (target response). These could be trained jointly
or as separate stages.

## Problem

Should the model explicitly decide the conversational action before generating
the response (two-stage), or learn both implicitly in one SFT pass?

## Decision

**v1: single-stage SFT.** Action labels are stored as metadata and used for
stratified curation review and sliced evaluation — not as a training target.
The two-stage decomposition (explicit action classification → conditioned
generation) is designed for but deferred.

## Alternatives considered

- **Two-stage training now (classifier + conditioned generator):** more moving
  parts (two training runs, error compounding, twice the eval surface) before
  we know whether plain SFT transfers behavior at all. Premature — deferred.
- **Action token as a chain-of-thought prefix in SFT targets:** a cheap middle
  ground (e.g. target = `[ask_clarifying_question] …response…`). Plausible
  iteration if v1 SFT underperforms on behavior control; kept as the T12
  fallback, not the v1 design.
- **No action labels at all:** would blind the eval slices and the safety
  analysis. Rejected — labels cost little and pay off in T11 regardless.

## Consequences

- (+) v1 has exactly one training run and one variable vs baseline — the
  cleanest possible experiment.
- (+) Action labels still earn their keep in review prioritization and eval
  slicing.
- (−) If the model learns fluent text but wrong behavior (answers when it
  should clarify), v1 can only *detect* it, and the fix waits for an iteration.

## Validation

Decided by T11 evidence: systematic action errors in the slice breakdown would
promote the two-stage (or action-prefix) design to the approved T12 iteration.
