# Curation Strategy

**Status:** draft for human approval · **Stage:** T1 · **Date:** 2026-09-29

How raw conversations become trusted training data: automated triage proposes,
the human disposes, and everything rejected is kept as a negative with a reason.

## 1. Pipeline position

T5 (triage) → T6 (human review) → T7 (curated + negative stores).
Triage output is advisory metadata; only T6 decisions move records into stores.

## 2. Quality dimensions (v1 rubric)

Each dimension scored 1–5 by triage (higher = better), with these meanings:

| Dimension | 1 (worst) | 5 (best) |
|---|---|---|
| relevance | response ignores the patient's message | directly addresses it |
| response_quality | incoherent / unusable | clear, complete, well-formed |
| medical_plausibility | contradicts established medicine | consistent with it |
| safety | could cause harm if followed | harm-averse, hedges appropriately |
| unsupported_claims | states specifics with no basis | claims grounded in the conversation |
| hallucination | invents facts (history, labs, prior advice) | invents nothing |
| diagnostic_overreach | definitive diagnosis from thin evidence | no diagnosis, or correctly deferred |
| missing_critical_context | omits red flags / emergency signs | surfaces what matters |
| conversational_appropriateness | wrong move (answers when it should ask, …) | right behavior for the situation |
| empathy_tone | cold, dismissive, alarming | professional, calm, empathic |
| instruction_adherence | violates the response instructions | follows them |

Rationale for this exact set: the first four cover generic response value; the
middle four are the medical-epistemic core (the experiment's thesis is that
these are what raw data gets wrong); the last three cover conversational
behavior, which is what we train. Any dimension scoring ≤2 SHOULD push the
verdict toward REVIEW or REJECT — the triage prompt encodes this, and T5's
calibration sample (workflow AC-T5-2) checks whether it actually happens.

## 3. Triage verdicts

- **ACCEPT** — learnable as-is. Still subject to the T6 audit sample; never
  auto-promoted to curated.
- **REVIEW** — uncertain or fixable. The human approves, corrects, or rejects.
  Expected to be the largest bucket in v1.
- **REJECT** — unlearnable (unsafe, fabricated, irredeemably poor). Goes to the
  negative store with a reason code, never silently dropped.

Verdict calibration: the human grades 100 triaged records blind in T5; the
agreement rate is reported, not gated, in v1 — we are measuring the triage
instrument before trusting it.

## 4. Human review protocol (T6)

1. Work the queue in order: REVIEW verdicts → ACCEPT audit sample → REJECT audit.
2. For each record: **approve** (as-is), **correct** (edit response and/or
   action label; original preserved in `history`), or **reject** (assign a
   negative reason).
3. Corrections target the *smallest change that makes the example learnable*
   — fix the behavior, don't rewrite style.
4. Record reviewer id + timestamp on every decision (schema-enforced).

Tooling v1: JSONL review files + a small export/import script
(`src/review/`), reviewed in any editor/spreadsheet. A dedicated UI is
explicitly deferred (ADR-0005) — at ~2K rows it would cost more than it saves.

Throughput risk (Q5): if one reviewer cannot clear the queue, narrow the
dataset (fewer records, same bar) rather than sampling-approve unreviewed
records. The scope decision is recorded in the T6 gate.

## 5. Rejection criteria (when to REJECT, not correct)

- Unsafe content that correction cannot salvage (e.g. dangerous advice woven
  through a long response — rewriting it means authoring, not curating).
- Fabricated clinical facts where the true facts are unknowable from context.
- Conversation so incoherent/noisy that no defensible target response exists.
- Duplicates (exact) — keep one canonical copy, reject the rest as
  `irrelevant_response`? No: duplicates get their own handling in T8/T9 and
  are **not** negatives. Rejected-for-cause only.

## 6. Good vs bad examples

**Positive (curated):** demonstrates behavior worth imitating — ideally across
all action labels, including `refuse_unsafe_request` and
`advise_professional_evaluation` (safe behavior must be *represented*, not just
evaluated).

**Negative (negative store):** demonstrates failure, with:

- the original failing response (preserved verbatim),
- a `negative_reason` from the closed vocabulary,
- the corrected response when one exists (future `chosen` for preference pairs),
- full provenance (negatives are evidence, not trash).

Negatives are excluded from SFT and reserved for eval slices, failure
analysis, and future preference tuning — see ADR-0008.

## 7. Provenance through curation

- Triage verdicts append a `T5` history entry (model, prompt version, verdict).
- Review decisions append a `T6` entry (reviewer, decision, timestamp).
- Corrections store the original text in the history entry, never overwrite.
- Store assignment (T7) appends a `T7` entry with the store name + manifest hash.
