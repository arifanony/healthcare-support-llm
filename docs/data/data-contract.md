# Data Contract

**Status:** draft for human approval · **Stage:** T1 · **Date:** 2026-09-29

Draft JSON/JSONL schemas for every pipeline stage. All records are JSON
objects, one per line in `.jsonl` files, UTF-8. Field rules: **required**
(must be present, gate fails otherwise), **optional** (may be absent),
**append-only** (history arrays — entries added, never edited).

Conventions: ids per [data-architecture.md](../architecture/data-architecture.md)
§4; timestamps RFC 3339 UTC; enums are lowercase snake_case, closed (unknown
value = validation error).

## 1. `conversation/v1` — normalized conversation (T3)

```jsonc
{
  "schema_version": "conversation/v1",   // required
  "conversation_id": "c-9f3a…",          // required, hash of normalized text
  "source_id": "meddialog:12345",        // required
  "turns": [                             // required, non-empty, alternating roles
    {"role": "patient", "text": "…"},
    {"role": "doctor", "text": "…"}
  ],
  "meta": {                              // required
    "source_rows": 1,
    "quarantined": false,                // true only with quarantine_reason
    "quarantine_reason": null            // optional enum when quarantined
  },
  "history": [                           // required, append-only
    {"stage": "T3", "action": "normalize", "actor": "script:structuring/normalize.py",
     "timestamp": "…", "detail": "…"}
  ]
}
```

## 2. `atomic/v1` — atomic decision-point example (T4)

One record = one patient message + the behavior it demands + the target response.

```jsonc
{
  "schema_version": "atomic/v1",         // required
  "example_id": "e-1a2b3c…",            // required, deterministic (source_id+span+version)
  "conversation_id": "c-9f3a…",         // required, exactly one parent
  "source_id": "meddialog:12345",       // required, denormalized for leak checks
  "context": "…",                       // required, relevant prior turns (may be "")
  "user_message": "…",                  // required, current patient message
  "action": "ask_clarifying_question",  // required, closed enum (§5)
  "response": "…",                      // required, target assistant response
  "metadata": {                         // required
    "quality": "unreviewed",            // required enum: unreviewed|approved|corrected|rejected
    "review_status": "pending",         // required enum: pending|human_approved|human_corrected|human_rejected
    "reviewer": null,                   // required when human_* (name/id)
    "reviewed_at": null,                // required when human_* (timestamp)
    "triage": null,                     // T5 verdict object (§4), null before T5
    "safety_flags": [],                 // required, list of closed-enum strings (§6)
    "negative_reason": null             // required-non-null iff in negative store (§7)
  },
  "history": []                         // required, append-only provenance trail
}
```

## 3. Curated / negative records (T7)

Same as `atomic/v1` plus store invariants (checked by the T7 gate, not new fields):

- curated: `metadata.review_status ∈ {human_approved, human_corrected}`,
  `reviewer` + `reviewed_at` present, `negative_reason` null.
- negative: `metadata.review_status = human_rejected` (or triage-rejected with
  audit), `negative_reason` ∈ closed vocabulary (§7), corrected response if one
  exists goes in `history[].detail.corrected_response` (never overwrites `response`).

## 4. Triage verdict object (T5, embedded in `metadata.triage`)

```jsonc
{
  "verdict": "REVIEW",                  // required enum: ACCEPT|REVIEW|REJECT
  "dimensions": {                       // required, each 1–5 + optional flag
    "relevance": 4, "response_quality": 3, "medical_plausibility": 4,
    "safety": 2, "unsupported_claims": 2, "hallucination": 1,
    "diagnostic_overreach": 2, "missing_critical_context": 3,
    "conversational_appropriateness": 4, "empathy_tone": 4,
    "instruction_adherence": 3
  },
  "rationale": "…",                     // required, ≤500 chars
  "prompt_version": "triage/v1",        // required
  "model": "…",                         // required, triage model id
  "created_at": "…"                     // required
}
```

Dimension semantics live in [curation-strategy.md](curation-strategy.md) §2.
Score direction: **higher = better** on every dimension (a `safety: 1` record
is dangerous). `REJECT` SHOULD correlate with low safety/plausibility, but the
verdict is the triage model's call — the human has the final word (T6).

## 5. Action-label vocabulary (closed, v1)

```text
answer  ask_clarifying_question  acknowledge  provide_general_information
request_more_context  advise_professional_evaluation  refuse_unsafe_request
respond_cautiously
```

- `request_more_context` vs `ask_clarifying_question`: the former asks for
  facts/records, the latter for disambiguation — kept distinct because the
  eval slices on them separately.
- New labels require a schema minor bump + ADR note; relabeling past records
  is a migration, never silent.

## 6. Safety flags (closed, v1)

```text
none  unvalidated_claim  diagnosis_stated  treatment_recommended
dosage_mentioned  emergency_signs_present  disallowed_content  pii_present
```

`emergency_signs_present` marks conversations where the correct behavior almost
certainly involves urging urgent professional care — prime golden candidates.

## 7. Negative-reason vocabulary (closed, v1)

```text
unsafe_response  unsupported_diagnosis  hallucination  irrelevant_response
insufficient_clarification  overconfident_answer  missing_important_context
inappropriate_tone
```

## 8. Manifests and locks

`MANIFEST.json` (every data store directory):

```jsonc
{
  "store": "curated", "created_at": "…", "producer": "script:…",
  "config_hash": "sha256:…",
  "files": [{"path": "curated.jsonl", "sha256": "…", "rows": 1234}]
}
```

`GOLDEN_LOCK.json` (`data/golden/`, see data-architecture §3):

```jsonc
{
  "golden_version": "g1", "locked_at": "…", "locked_by": "…",
  "sha256": "…", "row_count": 150,
  "criteria": "…", "baseline_run": "experiments/baseline/"
}
```

## 9. Training job spec (draft shape, finalized at T10)

```yaml
run_id: "20261001-qwen15b-lora-r1"
base_model: "Qwen/Qwen2.5-1.5B-Instruct"
datasets:
  train: {path: data/splits/train.jsonl, sha256: "…"}
  validation: {path: data/splits/validation.jsonl, sha256: "…"}
method: lora
lora: {r: 16, alpha: 32, dropout: 0.05, target_modules: [q_proj, v_proj]}
training: {epochs: 3, lr: 2.0e-4, batch_size: 4, grad_accum: 4, seed: 42}
decoding: {temperature: 0, max_new_tokens: 256}
backend: {type: colab, gpu: any, timeout_min: 360}
expected_outputs: [adapter_model.safetensors, tokenizer/, metrics.json, train.log]
```

## 10. Change policy

- Additive optional fields: minor bump, no migration.
- Renames, removals, enum changes: major bump + migration script + ADR entry.
- Every contract change lists affected stores and whether re-derivation is required.
