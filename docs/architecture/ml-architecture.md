# ML Architecture

**Status:** draft for human approval · **Stage:** T1 · **Date:** 2026-09-29

Model strategy: baseline → LoRA/QLoRA SFT → same-golden comparison,
with preference tuning as a designed-but-deferred future.

## 1. Experiment design

```text
BASE MODEL ─┬─► golden eval ───────────────────────► BASELINE RESULTS (locked)
            │
            └─► SFT on curated train ──► ADAPTER ──► golden eval ──► COMPARISON
                       ▲                                  │
                  validation split                   identical golden set,
                  (early stopping)                   identical harness
```

- The golden set, eval harness, and scoring rubric are frozen before Pass 1
  and reused byte-identically in Pass 2.
- Only one variable changes between passes: the adapter.
- A clean negative result (no improvement) is a valid outcome; §6 covers
  what we learn from it.

## 2. Base model shortlist (provisional — final pick at T10)

Selection criteria, in priority order: (a) fits free-Colab LoRA training,
(b) instruction-tuned variant exists, (c) permissive license, (d) strong
fine-tuning ecosystem (Transformers + PEFT + TRL, Unsloth-supported),
(e) context ≥ 4K tokens.

| Candidate (family) | Params | VRAM note (QLoRA-4bit) | License | Remarks |
|---|---|---|---|---|
| Llama-3.2-1B/3B-Instruct | 1B / 3B | 1B trivial; 3B fits T4-16GB | Llama Community | strong ecosystem; 1B safest for free tier |
| Qwen2.5-1.5B/3B-Instruct | 1.5B / 3B | fits T4-16GB | Apache-2.0 | long context (32K); good instruction following |
| SmolLM2-1.7B-Instruct | 1.7B | easily fits | Apache-2.0 | small, fast iteration; weaker baseline |
| Phi-3.5-mini-Instruct | 3.8B | tight on free T4, needs QLoRA+accum | MIT | strong quality; highest VRAM risk |

**Provisional direction:** Qwen2.5-1.5B/3B-Instruct or Llama-3.2-3B-Instruct,
decided at T10 after a VRAM probe on the actual backend. The final pick is
recorded in the training job spec, not here. Rationale for staying small:
see ADR-0001 and ADR-0009.

Open: Q2 in the problem statement tracks this decision.

## 3. Fine-tuning: LoRA/QLoRA SFT (v1)

- **Method:** supervised fine-tuning with LoRA adapters (rank/alpha/dropout in
  job spec; provisional r=16, α=32); QLoRA (4-bit NF4) if VRAM requires it.
  Executed via **Unsloth** (ADR-0013); vanilla TRL + PEFT is the fallback.
- **Data format:** instruction/chat templates of the chosen base model;
  atomic examples rendered as
  `history + patient message → target response` (single-turn; ADR-0002).
- **Action labels** (`ask_clarifying_question`, …) are stored as metadata in
  v1 and used for stratified eval — **not** as an auxiliary training target
  (ADR-0003). Revisit two-stage training only if SFT underperforms on
  behavior control.
- **Negatives excluded** from SFT (ADR-0008).
- **Validation:** held-out split for checkpoint selection; early stopping on
  validation loss; overfitting expected and monitored at this scale.
- **Seeds:** all seeds fixed and recorded; one seed in v1 (multi-seed only if
  time permits — state it as a limitation, not a silent gap).

## 4. Inference / eval decoding

- Baseline and fine-tuned runs share one decoding config
  (provisional: temperature 0, max_new_tokens bounded, fixed chat template).
- Sampling-based metrics (if any) use fixed seeds and N≥3; greedy decoding is
  the default to keep the comparison deterministic.

## 5. Evaluation interface (model-side)

The eval harness consumes any causal-LM checkpoint + tokenizer through a thin
adapter:

```text
generate(prompt: str, decoding: DecodingConfig) -> str
```

Base model, fine-tuned adapter, and any future iteration all implement this
interface, so T11 code never branches on model identity. Scoring dimensions
and comparison methodology live in
[docs/evaluation/evaluation-strategy.md](../evaluation/evaluation-strategy.md).

## 6. Interpreting outcomes

| Outcome | Reading | Next step (T12) |
|---|---|---|
| Fine-tuned > baseline clearly | curation + SFT transferred behavior | error analysis on remaining failures; consider iteration |
| Fine-tuned ≈ baseline | signal too weak / data too noisy / eval insensitive | slice analysis by action label; improve eval or curation |
| Fine-tuned < baseline | overfitting, template mismatch, or bad data slipped through | inspect regressions; audit curated slice; check template |

All three outcomes produce a documented iteration proposal — that is the T12
deliverable, not a rescue plan.

## 7. Future: preference tuning (designed, deferred)

The negative store (`data/negative/`) is shaped from day one to become
preference pairs (`chosen` = corrected/approved response, `rejected` =
original failure + reason). The v1 pipeline does not run DPO/ORPO; it only
guarantees the data will support it later. See ADR-0008.
