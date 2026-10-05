# Data Architecture

**Status:** draft for human approval · **Stage:** T1 · **Date:** 2026-09-29

How data moves, freezes, and proves its lineage:
raw → processed → curated → splits/golden.

## 1. Stores and their rules

| Store | Path | Write rule | Content |
|---|---|---|---|
| raw | `data/raw/` | **write-once, then immutable** | source files exactly as obtained + `MANIFEST.json` (URL, date, license, SHA-256 per file) |
| processed | `data/processed/` | reproducible from raw | normalized conversations + atomic examples (schema v1) |
| curated | `data/curated/` | human-approved only | training-worthy examples + provenance |
| negative | `data/negative/` | human- or triage-rejected | failure examples + reason codes (never in SFT) |
| splits | `data/splits/` | deterministic script output | `train.jsonl`, `validation.jsonl` + split manifest |
| golden | `data/golden/` | **locked, versioned** | `golden.jsonl` + lock record; eval-only |

Immutability is enforced socially (convention + review) and mechanically
(read-only checks in the T8 gate script, which re-hashes `raw/` and `golden/`
and fails on mismatch). See ADR-0004, ADR-0007.

## 2. Provenance model

Every example at every derived stage carries:

```text
source_id        stable id of the source conversation (e.g. "<dataset>:<row>")
parent_ids       ids of the immediate upstream record(s)
example_id       deterministic: sha256(source_id + turn_span + schema_version)[:16]
schema_version   contract version this record was written under
history          append-only list of {stage, action, actor, timestamp, detail}
```

Rules:

- `example_id` is deterministic so re-running extraction yields identical ids.
- `history` is append-only: corrections add entries, never rewrite past ones.
- A curated record must trace `curated → processed → raw` without gaps;
  the T7 gate script verifies the chain for every record.
- Splits record `{curated_manifest_hash, seed, grouping_key, ratios}` so any
  split file regenerates bit-identically.

See ADR-0006.

## 3. Versioning

- **Schemas:** `schema_version` (`atomic/v1`, …). Breaking changes bump the
  version; migration scripts convert forward, old files stay untouched.
- **Datasets:** each store directory carries `MANIFEST.json`
  (`{files: [{path, sha256, rows}], created_at, producer, config_hash}`).
- **Golden:** `data/golden/GOLDEN_LOCK.json`
  (`{version, locked_at, locked_by, sha256, row_count, criteria}`).
  Unlocking requires a new version + human approval + re-baseline note.
- **Code+config:** every manifest records the producing script name and the
  config hash, so provenance spans data *and* procedure.

## 4. Identifiers

| Id | Scope | Format |
|---|---|---|
| `source_id` | global | `<dataset-slug>:<source-row-key>` |
| `conversation_id` | processed+ | `c-<12 hex>` (hash of source text) |
| `example_id` | atomic+ | `e-<16 hex>` (deterministic, see §2) |
| `split_run_id` | splits | `split-<yyyymmdd>-<seed>` |
| `golden_version` | golden | `g1`, `g2`, … (monotonic) |
| `run_id` | experiments | `<yyyymmdd>-<slug>-<n>` |

## 5. Split integrity

Splitting happens on **conversation groups**, never on shuffled rows:

1. Deduplicate: exact-hash dedup on normalized text; near-dup detection
   (method TBD in T9 — provisional: normalized SimHash/embeddings threshold,
   recorded in ADR + config).
2. Group: all atomic examples from one source conversation share a group key.
3. Stratify (best effort): spread action labels and quality bands across splits.
4. Allocate groups to train/validation/golden at ~80/10/10, resolving the
   golden subset by human approval (T9), not pure randomness.
5. Verify: automated contamination check — no `source_id`, `conversation_id`,
   or normalized-text hash may appear in more than one split; golden hashes
   must match `GOLDEN_LOCK.json`.

Golden candidates are drawn from the highest-confidence human-approved pool;
final membership is a human decision (T9 gate).

## 6. Storage formats

- Working format: **JSONL**, one record per line, UTF-8. Human-diffable,
  streamable, tool-agnostic.
- Manifests/locks/configs: **JSON** (manifests) and **YAML** (human-edited configs).
- No database in v1: at ~2K rows, files + scripts beat infrastructure.
  (Revisit only if scale exceeds ~100K rows — record if so.)

## 7. Scale estimate (v1)

~2,000 source conversations → roughly 2,000–6,000 atomic examples (depends on
turns-per-conversation; measured in T4) → after triage/review, an estimated
1,000–4,000 curated + 100–200 golden. All well within JSONL-on-disk.
