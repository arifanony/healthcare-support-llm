# Problem Statement

**Status:** draft for human approval · **Stage:** T1 · **Date:** 2026-09-29

## 1. Precise problem definition

Build a **conversational medical Small Language Model (SLM)** as a learning
experiment: starting from ~2,000 raw medical conversation examples, design and
execute an end-to-end pipeline — curation, quality control, golden evaluation
data, baseline measurement, parameter-efficient fine-tuning, evaluation, and
one iteration loop — that produces a model measurably better at *conversational
behavior* in medical contexts than its base model, on a fixed golden set.

The model's task at inference time:

```text
conversation history + current patient message + relevant context
        → understand the conversational situation
        → determine the appropriate response behavior/action
        → generate an appropriate response
```

## 2. Objectives

1. **O1 — Demonstrate the full SLM lifecycle** on a small, reproducible scale.
2. **O2 — Build a working curation pipeline** that separates learnable examples
   from noisy, unsafe, or unsupported ones (raw → atomic → triage → human
   review → curated store).
3. **O3 — Establish a locked golden evaluation set** (~100–200 examples,
   evidence-based final count) used identically for baseline and fine-tuned models.
4. **O4 — Measure a baseline** with the chosen base SLM on the golden set
   *before* fine-tuning.
5. **O5 — Run one LoRA/QLoRA fine-tuning experiment** on curated data and
   compare against the baseline on the same golden set.
6. **O6 — Document every major decision** as an ADR and every stage transition
   with acceptance criteria.

## 3. Non-objectives (constraints on scope)

- The model is **not** a diagnostician: no autonomous diagnosis, triage
  scoring, or treatment recommendation is designed, trained, or evaluated.
- No production serving, API, mobile app, or user-facing deployment.
- No real patient data: only public/research conversation datasets.
- No claim of medical safety certification of any kind.

## 4. Behavioral targets

The model should learn:

- conversational behavior and contextual response generation
- asking appropriate clarifying questions
- response relevance and communication quality
- safety-aware behavior (hedging, deferring to professionals, refusing unsafe requests)
- avoiding unsupported claims

Observable failure modes to suppress (see also
[docs/data/curation-strategy.md](../data/curation-strategy.md)):

- unsafe responses, unsupported diagnoses, hallucinations
- irrelevant or overconfident answers
- missing critical context, insufficient clarification
- inappropriate tone

## 5. Constraints

| ID | Constraint |
|---|---|
| C1 | Personal-use research; local-first; minimal cost (free Colab GPU tier if possible) |
| C2 | Source data immutable; all derived data carries provenance |
| C3 | Golden data never used for training; locked and versioned |
| C4 | Human is final authority on data acceptance, results, and model versions |
| C5 | Reproducible: seeded splits, hashed datasets, checked-in job specs |
| C6 | Small scale first: ~2K examples, SLM-size base model, LoRA/QLoRA |
| C7 | No training code or dataset download during the architecture phase |

## 6. Assumptions (to validate)

| ID | Assumption | Validation stage |
|---|---|---|
| A1 | ~2K source conversations are obtainable with a usable license | T2 |
| A2 | A large fraction of raw examples will need correction or rejection | T5–T6 |
| A3 | Free-tier Colab GPU suffices for LoRA on a 1–3B model | T10 |
| A4 | 100–200 golden examples suffice to distinguish baseline from fine-tuned | T8–T9 |
| A5 | Atomic decision-point examples train better than whole conversations | T4, T11 |

## 7. Success criteria

**Phase gate (this document, T1):**

- [x] AC-T1-1: problem statement, architectures, workflow, contracts, ADRs, diagrams exist
- [ ] AC-T1-2: human approves the T1 document set

**Project-level (experiment success):**

- AC-P-1: golden set locked with provenance; zero leakage into train/val (verified by script)
- AC-P-2: baseline results recorded on the golden set before any fine-tuning
- AC-P-3: one fine-tuning run completes with artifacts (adapter, metrics, logs) in `experiments/`
- AC-P-4: fine-tuned model evaluated on the *identical* golden set; comparison documented
- AC-P-5: error analysis identifies at least one concrete curation or training improvement
- AC-P-6: full run reproducible from checked-in specs + hashed datasets

Note: "fine-tuned beats baseline" is **not** a success criterion — a clean
negative result with error analysis still satisfies O1.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Raw data quality too poor to yield 2K usable examples | Triage + human review gate; shrink scope honestly if needed |
| Golden set too small/noisy to discriminate models | Evidence-based sizing in T8; report confidence honestly |
| Colab free tier insufficient | Fallback: smaller model, QLoRA-4bit, gradient accumulation, or Kaggle GPU |
| Leakage between splits | Conversation-level grouping + dedup + automated contamination check |
| Scope creep into diagnosis | Behavioral targets + refusal/clarification actions; eval has no diagnosis-accuracy metric |

## 9. Open questions (must resolve before T2/T3 implementation)

1. **Q1:** Which source dataset? (Candidates to compare: MedDialog, MTS-Dialog,
   ChatDoctor/HealthCareMagic-derived sets, others — license + format + quality.)
2. **Q2:** Exact base model shortlist and final pick (see
   [docs/architecture/ml-architecture.md](../architecture/ml-architecture.md) §2).
3. **Q3:** Single-turn atomic examples only, or include multi-turn targets? (Provisional: single-turn — ADR-0002.)
4. **Q4:** Is the two-stage action→response decomposition used in training or
   only as eval metadata? (Provisional: metadata-only — ADR-0003.)
5. **Q5:** Human review throughput: can one reviewer clear ~2K triaged examples?
   Sampling strategy if not.
6. **Q6:** Colab vs Kaggle vs local GPU — what is actually available at T10 time?
