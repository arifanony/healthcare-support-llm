# Evaluation Strategy

**Status:** draft for human approval · **Stage:** T1 · **Date:** 2026-09-29

How we know whether fine-tuning helped: a locked golden set, a frozen harness,
and a comparison methodology that reports honestly at small-n.

## 1. Golden dataset

- **Source:** highest-confidence human-approved records (T6), membership
  approved by the human at T9 and frozen in `GOLDEN_LOCK.json`.
- **Size:** ~100–200, evidence-based: large enough to cover all action labels
  (≥8–10 examples each) plus safety-critical slices
  (`emergency_signs_present`, `refuse_unsafe_request`), small enough to lock
  with genuine confidence. Final count justified in the lock record (AC-T9-4).
- **Invariants:** never in train/val (hash-verified); identical bytes for
  baseline and comparison evals; re-versioned (never edited) on change.
  See ADR-0007.

## 2. What is measured (quality dimensions)

Per-example scoring reuses the curation rubric where applicable, scored by a
mix of human grading and scripted checks:

| Dimension | Method in v1 |
|---|---|
| action correctness (did it take the right conversational action?) | human grade on golden outputs |
| response relevance | human grade |
| safety (no unsafe content; correct refusal/hedge where needed) | human grade + flag census |
| unsupported claims / hallucination present? | human grade (binary per example) |
| clarifying-question quality (when the action demands it) | human grade |
| empathy/tone | human grade (coarse: ok / off) |
| verbatim leakage (train text regurgitated)? | scripted n-gram overlap check |

Deliberately absent: diagnosis accuracy (not our task), BLEU/ROUGE-style
overlap metrics as primary signals (they correlate poorly with behavior at
this scale — may be reported as auxiliary numbers only), LLM-as-judge in v1
(unvalidated judge + small-n = noise; revisit with a validated judge in an
iteration).

## 3. Comparison methodology

1. Freeze: golden bytes, eval harness, decoding config, rubric — before T11a.
2. T11a: base model generates on golden prompts → human grades → baseline
   results locked.
3. T11b: fine-tuned model generates on identical prompts/same decoding →
   same grader, same rubric → comparison report.
4. Report: aggregate win/tie/loss per dimension, slice-by-action-label tables,
   safety-flag census, and the full per-example grading sheet (so the human
   can spot-check any claim).
5. Statistics: at n≈150, report raw counts + simple paired comparison
   (McNemar or paired bootstrap); no p-hacking — the sample is what it is,
   and "no detectable difference" is a reportable outcome.

## 4. Safety checks (hard gates on reporting, not on training)

- Any unsafe generation in T11b is flagged in the report regardless of
  aggregate scores; a model that improves on average but introduces unsafe
  outputs is reported as a regression-with-improvement, and the human decides.
- Golden safety-critical slices are reported separately, never averaged away.

## 5. Baseline discipline

- The baseline runs **before** any fine-tuning result is known, on the same
  harness that will score the comparison. Its outputs and grades are locked
  (`experiments/baseline/`, hashes recorded) so later disappointment cannot
  revise them.
- Decoding config equality between T11a and T11b is verified by script
  (AC-T11-2), not by memory.

## 6. Threats to validity (stated upfront)

- Small-n golden set: low power; fine differences are undetectable by design.
- Single grader (the human): consistent but possibly biased; mitigated by the
  frozen rubric and the full grading sheet.
- Single seed / single run in v1: run-to-run variance unmeasured — stated as
  a limitation in every report.
- Golden coverage ≠ real-world coverage: the golden set measures the behaviors
  we curated for, nothing more.
