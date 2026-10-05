# T1–T12 Workflow

**Status:** draft for human approval · **Stage:** T1 · **Date:** 2026-09-29

The authoritative stage contract. Each stage lists inputs, outputs, acceptance
criteria (gates), failure conditions, and state transitions. The proposed T1–T12
breakdown is **accepted as-is** for v1 — no stage added, removed, or merged
(see §13 for the one structural note on T7/T8 ordering).

State vocabulary (all stages):
`queued → pending → active → completed`, with `rejected` (gate failed, needs
rework) and `stale` (upstream changed, re-verification required).

## T1 — Problem and System Definition

- **Inputs:** project brief (this task), host environment facts.
- **Outputs:** README, problem statement, architectures, workflow (this file),
  data contracts, ADRs, diagrams, `.genesis/` scaffold.
- **Acceptance:**
  - [ ] AC-T1-1: all §18 documents of the brief exist and cross-link.
  - [ ] AC-T1-2: human approves the T1 set (explicit sign-off).
  - [ ] AC-T1-3: no code in `src/` beyond scaffolding; no data downloaded.
- **Failure:** approval withheld → revise docs, stay in T1.
- **Transition:** on AC-T1-2 → T1 `completed`, T2 `pending`.

## T2 — Source Data Ingestion

- **Inputs:** dataset choice (resolves Q1), T1 approval.
- **Outputs:** `data/raw/` files + `MANIFEST.json` (source URL, retrieval date,
  license, SHA-256 per file, row count).
- **Acceptance:**
  - [ ] AC-T2-1: manifest present; every file hash-verified.
  - [ ] AC-T2-2: license recorded and compatible with personal research use.
  - [ ] AC-T2-3: `data/raw/` marked read-only (gate script fails on later mutation).
- **Failure:** unusable license/format → pick another source, re-run T2.
- **Transition:** → T3 `pending`.

## T3 — Data Structuring

- **Inputs:** `data/raw/` + manifest.
- **Outputs:** `data/processed/conversations.jsonl` (normalized, schema
  `conversation/v1`) + manifest.
- **Acceptance:**
  - [ ] AC-T3-1: 100% of raw rows mapped or explicitly quarantined with reason.
  - [ ] AC-T3-2: schema validation passes on every record.
  - [ ] AC-T3-3: re-run is byte-identical (determinism check).
- **Failure:** >5% quarantine rate → inspect source assumptions, revise mappings.
- **Transition:** → T4 `pending`.

## T4 — Atomic Decision-Point Extraction

- **Inputs:** normalized conversations.
- **Outputs:** `data/processed/atomic.jsonl` (schema `atomic/v1`: history +
  user message + target response + provisional action label + provenance).
- **Acceptance:**
  - [ ] AC-T4-1: every atomic record links to exactly one parent conversation.
  - [ ] AC-T4-2: turn-span coverage report: % of conversation turns represented.
  - [ ] AC-T4-3: spot-check 50 records by human: extraction errors <10% or revise rules.
- **Failure:** systematic span errors → fix extractor, re-run (cheap: deterministic).
- **Transition:** → T5 `pending`.

## T5 — Automated LLM Data Triage

- **Inputs:** atomic records + triage config (`configs/triage.yaml`: rubric,
  model, prompt version).
- **Outputs:** triage verdicts (`ACCEPT`/`REVIEW`/`REJECT` + dimension scores +
  rationale) joined to records; triage report (distributions, model/prompt id).
- **Acceptance:**
  - [ ] AC-T5-1: verdict on 100% of records; config + prompt version recorded.
  - [ ] AC-T5-2: calibration sample — human grades 100 triaged records; triage↔human
    agreement measured and reported (no pass threshold in v1, but must be reported).
  - [ ] AC-T5-3: REJECT reasons use only the controlled vocabulary.
- **Failure:** triage output unparseable at scale → fix prompt/parser, re-run.
- **Transition:** → T6 `pending`. Note: triage never writes to curated stores.

## T6 — Human Review and Correction

- **Inputs:** triaged records, prioritized (REVIEW first, then ACCEPT sample, then REJECT audit).
- **Outputs:** review decisions (`human_approved` / `human_corrected` /
  `human_rejected` + corrected text where applicable), merged into records.
- **Acceptance:**
  - [ ] AC-T6-1: every REVIEW-verdict record has a human decision.
  - [ ] AC-T6-2: ≥10% audit sample of ACCEPT verdicts reviewed (or full review —
    decide in T6 planning, record the choice).
  - [ ] AC-T6-3: no record carries `human_approved` without a named reviewer + timestamp.
- **Failure:** reviewer throughput insufficient → narrow scope (fewer records, same
  bar) rather than lowering the bar; record the scope change.
- **Transition:** → T7 `pending`.

## T7 — Curated Label Store + Provenance

- **Inputs:** reviewed records.
- **Outputs:** `data/curated/curated.jsonl` + manifest;
  `data/negative/negatives.jsonl` + manifest (with reason codes).
- **Acceptance:**
  - [ ] AC-T7-1: curated contains only `human_approved`/`human_corrected` records.
  - [ ] AC-T7-2: provenance chain verified for 100% of records
    (curated → processed → raw unbroken).
  - [ ] AC-T7-3: negatives carry a reason code + link to source; none appear in curated.
- **Failure:** chain gaps → fix upstream ids, rebuild (raw untouched).
- **Transition:** → T8 `pending`.

## T8 — Epistemic / Dataset Quality Checks

- **Inputs:** curated + negative stores.
- **Outputs:** quality report (label/action distributions, length stats, dedup
  report, leakage pre-scan, safety-flag census) + go/no-go for splitting.
- **Acceptance:**
  - [ ] AC-T8-1: report generated from a checked-in script + config.
  - [ ] AC-T8-2: exact-duplicate groups resolved (dropped or merged, recorded).
  - [ ] AC-T8-3: human acknowledges the report (go/no-go recorded).
- **Failure:** no-go → loop back to T6 (targeted re-review) or T4 (re-extract);
  downstream stages go `stale`.
- **Transition:** on go → T9 `pending`.

## T9 — Train / Validation / Golden Split

- **Inputs:** curated store + split config (`configs/split.yaml`: seed, ratios,
  grouping key, near-dup method).
- **Outputs:** `data/splits/{train,validation}.jsonl` + split manifest;
  `data/golden/golden.jsonl` + `GOLDEN_LOCK.json`.
- **Acceptance:**
  - [ ] AC-T9-1: split regenerates byte-identically from config + curated manifest.
  - [ ] AC-T9-2: contamination check passes: no shared `source_id` /
    `conversation_id` / text-hash across the three sets.
  - [ ] AC-T9-3: golden membership human-approved; lock file signed (name + date).
  - [ ] AC-T9-4: golden size justified in the lock record (evidence-based, ~100–200).
- **Failure:** contamination found → fix grouping/dedup, re-run; golden lock waits.
- **Transition:** → T10 and T11-baseline `pending` (baseline needs only golden + base model).

## T10 — GPU Training Execution

- **Inputs:** training job spec (`experiments/<run>/job.yaml`: dataset hashes,
  base model, hyperparams, seed) + human approval of the spec.
- **Outputs:** adapter + tokenizer + metrics + logs in `experiments/<run>/`;
  artifact bundle in `artifacts/`.
- **Acceptance:**
  - [ ] AC-T10-1: job spec approved *before* launch; dataset hashes match manifests.
  - [ ] AC-T10-2: training completed or resumed-to-completion; attempt history recorded.
  - [ ] AC-T10-3: artifacts present with hashes; val loss curve sane (no NaN/divergence
    accepted silently — a diverged run is a *reported* failed run, not a deleted one).
- **Failure:** diverged/lost session → record, diagnose, relaunch as a new attempt
  under the same run id; never overwrite.
- **Transition:** → T11 `pending`.

## T11 — Model Evaluation

Two ordered evaluations, same harness, same golden bytes:

- **T11a baseline:** base model × golden → `experiments/baseline/results.json` (locked).
- **T11b comparison:** fine-tuned adapter × golden → comparison report.
- **Inputs:** golden set + lock, eval config (`configs/eval.yaml`), model artifact(s).
- **Outputs:** per-example scores, aggregate + sliced metrics, comparison report,
  human accept/reject of the result.
- **Acceptance:**
  - [ ] AC-T11-1: golden hash at eval time equals lock hash.
  - [ ] AC-T11-2: decoding config identical across T11a/T11b (diffed by script).
  - [ ] AC-T11-3: report includes slice-by-action-label breakdown + safety-flag census.
  - [ ] AC-T11-4: human records accept/reject with reason.
- **Failure:** lock mismatch → halt, investigate; never "just re-run" on drifted data.
- **Transition:** → T12 `pending`.

## T12 — Error Analysis and Iteration

- **Inputs:** comparison report, per-example outputs, curated data.
- **Outputs:** error analysis note (`experiments/<run>/error-analysis.md`):
  failure clusters, suspected causes (data vs training vs eval), one concrete
  iteration proposal with predicted effect.
- **Acceptance:**
  - [ ] AC-T12-1: top failure clusters named with example ids.
  - [ ] AC-T12-2: iteration proposal states *what changes, what is measured,
    what would falsify it*.
  - [ ] AC-T12-3: human approves or closes the iteration (project may end here).
- **Failure:** n/a — analysis always completes; "no clear signal" is a valid finding.
- **Transition:** approved iteration → affected stages `stale`, loop re-enters;
  closed → project complete.

## 13. Structural notes

- **T1–T12 accepted as-is.** The proposed breakdown maps cleanly onto
  artifacts and gates; inventing a different numbering would add confusion
  without value (YAGNI). One ordering note: T7 (store) logically precedes T8
  (checks), but T8 findings loop back to T6/T4 — the loop is explicit in §T8,
  so no reorder needed.
- **Baseline placement:** T11a (baseline eval) can run as soon as T9 locks
  golden — it does not wait for T10. The workflow table in the README shows
  the dependency, not a strict sequence.
