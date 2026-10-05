# System Design

**Status:** draft for human approval · **Stage:** T1 · **Date:** 2026-09-29

End-to-end architecture of the medical conversational SLM experiment.
Companion diagrams: [diagrams/](../../diagrams/) (Mermaid sources).

## 1. System overview

Four subsystems, one human authority:

```text
                       ┌──────────────┐
                       │    HUMAN     │  final authority on data,
                       │  (reviewer)  │  results, model versions
                       └──────┬───────┘
                              │ approve / reject / correct
              ┌───────────────┼────────────────┐
              ▼               ▼                ▼
     ┌─────────────┐  ┌──────────────┐  ┌──────────────┐
     │    DATA     │  │   TRAINING   │  │  EVALUATION  │
     │  PIPELINE   │  │   PIPELINE   │  │   PIPELINE   │
     │  T2–T9      │  │    T10       │  │   T11–T12    │
     └──────┬──────┘  └──────┬───────┘  └──────┬───────┘
            │                │                 │
            ▼                ▼                 ▼
     curated splits   model adapter     comparison report
     + golden set     + metrics/logs    + error analysis
```

A lightweight state layer (Genesis, where available — see §6) tracks each
stage's status, inputs, outputs, and acceptance gates. It orchestrates; it
does not own data or logic.

## 2. Data flow (T2–T9)

```text
data/raw/          T2 ingestion        content-hash manifest, READ-ONLY after write
    │              (download + manifest; source files never touched again)
    ▼
data/processed/    T3 structuring      normalized conversations, schema v1
    │              T4 atomic extraction  single-turn decision-point examples
    ▼
triage queue       T5 automated triage ACCEPT / REVIEW / REJECT + rationale
    │
    ▼
review queue       T6 human review     approve / correct / reject (human decides)
    │
    ▼
data/curated/      T7 label store      approved examples + full provenance
data/negative/     T7 negative store   rejected examples + failure reason
    │
    ▼
quality gates      T8 epistemic checks distributions, dedup, leakage scan
    │
    ▼
data/splits/       T9 deterministic    train.jsonl / validation.jsonl (+manifest)
data/golden/       T9 golden lock      golden.jsonl, LOCKED, never for training
```

Details: [data-architecture.md](data-architecture.md),
[curation-strategy.md](../data/curation-strategy.md),
[data-contract.md](../data/data-contract.md).

## 3. Model flow (T10)

Two passes over the **same** golden set, separated in time:

```text
Pass 1 (baseline):   base model ──► golden eval ──► baseline results (locked)
Pass 2 (experiment): base model + curated train ──► LoRA/QLoRA ──► adapter
                                                  ──► golden eval ──► comparison
```

- Training executes on a remote GPU backend (Colab) from a declarative
  **training job spec** produced in this repo (see §5, ADR-0010).
- Only adapters + tokenizer + metrics + logs return; full-model weights are
  never stored in the repo.
- Validation split drives early stopping / checkpoint selection; the golden
  set is touched only for the two locked evaluations.

Details: [ml-architecture.md](ml-architecture.md).

## 4. Human-in-the-loop flow

The human appears at exactly three decision points — nowhere else is human
judgment required, everywhere else it is final:

1. **T6 — Data acceptance.** Triage proposes; the human approves, corrects, or
   rejects every curated example (sampling policy TBD in T6 if throughput
   forces it — see Q5).
2. **T9 — Golden lock.** The human approves the golden set contents; locking is
   explicit and versioned.
3. **T11/T12 — Result acceptance.** The human accepts or rejects the comparison
   outcome and decides whether a model version is kept.

Tooling (review UI/CLI, diff views) is deliberately minimal in v1: JSONL +
scripts over a spreadsheet-grade review loop. See ADR-0005.

## 5. GPU execution flow

```text
repo (local)                        GPU backend (Colab, later)
─────────────                        ─────────────────────────
job spec (YAML) ──────► upload ─────► provision runtime, install deps
train/val .jsonl ─────► upload ─────► run training script (from repo, pinned hash)
                                         │ checkpoint, metrics, logs
artifacts/ ◄──────── download ◄──────── adapter + tokenizer + metrics + logs
experiments/<run>/ ◄── record ─────── job spec copy + results + notes
```

The job spec is the contract: dataset hashes, base model id, hyperparameters,
seed, expected outputs. Re-running the same spec must reproduce the run
within hardware nondeterminism. Failed/disconnected sessions resume from the
last checkpoint; the spec records attempt history. See ADR-0010 and
[environment-design.md](environment-design.md).

## 6. State layer (Genesis)

Where Genesis tooling is available, each T-stage is a tracked task with:

- `inputs` — required artifacts/hashes
- `outputs` — produced artifacts/hashes
- `acceptance` — executable gate(s), e.g. `scripts/check_no_golden_leak.py`
- `state` — queued → pending → active → completed (or rejected/stale)

**Verified state (2026-09-29):** Genesis is initialized for this repo
(`genesis init D:\SLM --workflow new-product`), with live `project.json`,
`KICKOFF.md`, and agent connection (`AGENTS.md`, `CLAUDE.md`). The installed
CLI + kit live at `C:\Users\ARIF\tools` (used as-is; nothing reinstalled).
Sandbox note: the CLI's lockfile defaults to system Temp, which is denied in
sandboxed sessions — redirect `TEMP`/`TMP`/`TMPDIR` to a writable directory
before invoking `genesis`. Nothing in this design depends on Genesis
internals beyond the task/gate surface shown in `--help`.

Fallback: if Genesis ever becomes unavailable, stage state lives in
`experiments/` records + the checklist in
[t1-t12-workflow.md](../workflow/t1-t12-workflow.md) §12.
The pipeline scripts never import Genesis; state is metadata, not control flow.

## 7. Component map (repo → subsystem)

| Directory | Subsystem | Owns |
|---|---|---|
| `src/ingestion/` | data | download + manifest + hash verify |
| `src/structuring/` | data | normalize, atomic extraction |
| `src/curation/` | data | triage runner, quality checks |
| `src/review/` | data | review queue export/import, correction merge |
| `src/splitting/` | data | dedup, grouped split, leak check |
| `src/training/` | training | job-spec builder, Colab runner, artifact fetch |
| `src/evaluation/` | evaluation | golden runner, scorers, comparison report |
| `configs/` | all | dataset/triage/split/job/eval configs |
| `experiments/` | all | per-run evidence bundles |

## 8. Trust boundaries

1. **Raw data boundary:** `data/raw/` is write-once. Nothing downstream may
   modify it; violations fail the T8 gate.
2. **Golden boundary:** `data/golden/` is readable by evaluation only.
   Training code must not reference golden paths; the leak-check script
   enforces this on hashes, not just paths.
3. **Human boundary:** no automated step may mark data `human_approved`.
4. **Environment boundary:** the GPU backend receives data + spec, returns
   artifacts; it never edits repo state directly.
