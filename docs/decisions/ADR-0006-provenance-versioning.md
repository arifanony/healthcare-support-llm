# ADR-0006 — Provenance and additive labeling

**Status:** proposed (pending human approval) · **Date:** 2026-09-29 · **Stage:** T1

## Context

Regulators aren't watching, but reproducibility is: any number in the final
report must trace back to exact bytes through exact code.

## Problem

What is the cheapest provenance scheme that makes "show me where this example
/ number came from" executable rather than aspirational?

## Decision

- **Record-level:** deterministic `example_id`, `source_id` + `parent_ids` on
  every derived record, append-only `history[]` trail
  (stage/action/actor/timestamp/detail). Corrections append; nothing rewrites.
- **Dataset-level:** `MANIFEST.json` per store (file hashes, row counts,
  producer script, config hash); splits add seed + grouping + ratios;
  golden adds `GOLDEN_LOCK.json` (version, locker, hash, criteria).
- **Procedure-level:** manifests record producing-script name and config hash;
  experiments record job spec + `pip freeze` + harness commit.
- **No database, no DVC in v1:** JSONL + manifests + a verification script.

## Alternatives considered

- **Full data versioning (DVC / LakeFS):** correct at scale, unjustified at
  ~2K rows / MBs of data. Deferred with a trigger (data >1GB or multi-branch
  dataset work).
- **VCS-only provenance ("it's all in git history"):** conflates code and data
  versioning, breaks on large files, and can't answer "which config produced
  this split" without archaeology. Rejected as the mechanism.
- **Provenance-as-documentation (describe lineage in prose):** untestable.
  Rejected — every provenance claim in this project has a script that checks it.

## Consequences

- (+) Complete audit trail from golden score → golden row → curated row →
  review decision → triage verdict → atomic record → conversation → raw bytes.
- (+) Verification is `python scripts/verify_provenance.py`, not a manual audit.
- (−) Every pipeline script must write history entries and manifests —
  a small tax on each implementation, enforced by stage gates.
- (−) Deterministic ids + append-only history require care in re-runs
  (re-derivation must reproduce ids exactly — tested in T3/T4 gates).
