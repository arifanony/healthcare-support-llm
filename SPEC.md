# Product specification — SLM

> Status: draft. A coding agent must not implement product code until this specification is approved through Genesis.

## Problem

An individual researcher wants to learn and demonstrate the complete
Small Language Model engineering lifecycle — from raw medical conversations
to a fine-tuned, evaluated conversational model — on a small (~2K-example),
reproducible, local-first scale. Raw conversation data is uneven (poor,
unsafe, or unsupported responses mixed with good ones), so the pipeline must
curate before it trains, measure a baseline before fine-tuning, and compare
strictly on locked golden data. The model under study learns conversational
response behavior (context use, relevance, clarifying questions, tone,
safety-aware refusal); it is explicitly not an autonomous diagnostic or
treatment system.

Desired outcomes: (1) a working, gated T1–T12 pipeline; (2) a locked golden
set with a recorded baseline; (3) one LoRA/QLoRA experiment compared against
that baseline on identical golden data; (4) an error analysis with a concrete
iteration proposal; (5) every step reproducible from versioned specs and
hashed artifacts.

## Users

- The researcher/owner (sole user): runs the pipeline, performs human review,
  approves data, locks golden, accepts results. Also the only grader.
- The coding agent: implements pipeline code within Genesis tasks and gates;
  never approves data, results, or model versions.
- Future readers of the repo: learn the SLM lifecycle from docs, ADRs, and
  experiment records. No end-users, patients, or production consumers exist.

## Functional requirements

- FR-1: Ingest a source conversation dataset into a write-once raw store with a manifest (origin, date, license, SHA-256 per file).
- FR-2: Normalize raw conversations into a validated schema, quarantining unmappable rows with explicit reasons.
- FR-3: Extract atomic decision-point examples (history + patient message + action label + target response) with deterministic ids and parent links.
- FR-4: Automatically triage every atomic example to ACCEPT / REVIEW / REJECT with dimension scores and a rationale, recording model and prompt version.
- FR-5: Provide a human review queue showing source, atomic example, triage result, and reasons, accepting ACCEPT / EDIT / REJECT decisions with reviewer identity and timestamp.
- FR-6: Build a curated store (human-approved examples only) and a negative store (rejections with reason codes), both provenance-chained to source.
- FR-7: Run dataset quality checks (label distributions, exact-duplicate resolution, safety-flag census) producing a go/no-go report.
- FR-8: Produce deterministic, seeded train/validation/golden splits at conversation-group granularity with an automated cross-split contamination check.
- FR-9: Lock the golden set under explicit human approval with a versioned lock record; support re-versioning, never silent edits.
- FR-10: Evaluate the base model on the golden set with a frozen harness and record locked baseline results before any fine-tuning.
- FR-11: Fine-tune via LoRA/QLoRA from a declarative, human-approved job spec executed on a remote GPU backend, returning adapter, metrics, and logs.
- FR-12: Re-evaluate on the byte-identical golden set with the identical harness and produce a comparison report (aggregates, action-label slices, safety census, per-example grades).
- FR-13: Produce an error analysis naming failure clusters with example ids and one falsifiable iteration proposal.
- FR-14: Reproduce any dataset, split, or run from checked-in specs, seeds, and recorded hashes.

## Non-functional requirements

- NFR-1: Provenance completeness — 100% of curated, negative, and golden records trace unbroken to raw source, verified by script.
- NFR-2: Split integrity — zero shared source/conversation/text identity across train, validation, and golden, verified by script at split and eval time.
- NFR-3: Human authority — no automated step may mark data human-approved, lock golden, or accept results; every such act names a human and timestamp.
- NFR-4: Reproducibility — splits regenerate byte-identically from config; runs are described by checked-in specs with pinned code, deps, and seeds.
- NFR-5: Local-first economy — all logic runs locally except GPU training and optional bulk inference; v1 targets free-tier GPU.
- NFR-6: Change discipline — material decisions are recorded as ADRs (proposed until human-approved); stage transitions require their acceptance gates.
- NFR-7: Safety honesty — unsafe generations are flagged in reports regardless of aggregates; limitations (small-n, single grader, single seed) are stated, not hidden.

## Constraints

- Personal research budget: free-tier GPU first, with a human-decided fallback chain.
- Small scale: ~2K source examples; JSONL-on-disk; no database or data-versioning infrastructure in v1.
- Windows + VS Code local host; Python 3.11+; stdlib-first pipeline code; heavy ML deps are GPU-backend-only.
- Sandbox: the coding agent cannot reach the network or host Temp freely; dataset download, GPU spend, and approvals are human-authorized acts.
- Trust boundaries: raw store is write-once; golden store is eval-only; the GPU backend holds no repo state and no secrets.
- Regulatory: no real patient data; only public/research datasets with compatible licenses; no safety certification is claimed or implied.
- This is a personal research/learning project, not a production autonomous medical decision system; nothing here is for clinical use.

## Non-goals

- No autonomous diagnosis, triage scoring, or treatment recommendation — neither trained nor evaluated.
- No production serving, API, app, or deployment of any kind.
- No real patient data (no PHI ingestion path exists by design).
- No multi-seed / multi-run statistical program in v1 (single run, limitations stated).
- No LLM-as-judge, preference tuning, or two-stage training in v1 (designed for, explicitly deferred).
- No bespoke review UI in v1 (JSONL + scripts suffice at this scale).

## Acceptance criteria

- AC-1: Golden lock hash at eval time equals the recorded lock hash, verified by script.
- AC-2: Contamination check passes: no shared source/conversation/text identity across the three splits.
- AC-3: Provenance check passes: every curated, negative, and golden record chains to raw source.
- AC-4: Curated store contains only records with a named human approver and timestamp.
- AC-5: Baseline results exist with hashes and predate any fine-tuning result.
- AC-6: Decoding configs for baseline and comparison evals are script-verified identical.
- AC-7: The comparison report includes action-label slices, a safety-flag census, and the full grading sheet.
- AC-8: The error analysis names failure clusters with example ids and one falsifiable iteration proposal.
- AC-9: Train/validation splits regenerate byte-identically from the checked-in split config.
- AC-10: No training code, dataset download, or GPU execution occurred before spec and plan approval.

## Risks

- Raw data quality too poor to yield enough usable examples — mitigate with triage + human gate; narrow scope honestly rather than lowering the bar.
- Golden set too small to discriminate models — mitigate with evidence-based sizing and honest small-n reporting (AC-7, NFR-7).
- Free-tier GPU insufficient — mitigate with the fallback chain (smaller model, QLoRA-4bit, accumulation, Kaggle, paid tier; human decides).
- Reviewer throughput bottleneck — mitigate by scoping the dataset to what one reviewer can genuinely clear.
- Leakage across splits — mitigate with conversation-group splitting, dedup, and script-enforced checks (AC-2).
- Scope creep into diagnosis — mitigate by behavioral targets, refusal/clarification actions, and no diagnosis-accuracy metric anywhere.

## Open questions

- Q1: Which source dataset (license + format + quality comparison still to run)?
- Q2: Final base-model pick (shortlist exists; VRAM probe at T10 decides)?
- Q3: Single-turn atomic examples only, or include multi-turn targets (provisional: single-turn)?
- Q4: Is action→response decomposition used in training or as eval metadata only (provisional: metadata-only)?
- Q5: Can one reviewer clear the queue, or is a scope cut needed (decided at T6 planning)?
- Q6: Which GPU backend is actually available at T10 time (Colab free vs alternatives)?
