# ADR-0004 — Source-data immutability

**Status:** proposed (pending human approval) · **Date:** 2026-09-29 · **Stage:** T1

## Context

Every downstream artifact (normalized, atomic, curated, splits, golden, model)
derives from the raw source. If raw bytes change silently, all provenance is fiction.

## Problem

How do we guarantee the source data stays a fixed point for the project's lifetime?

## Decision

`data/raw/` is **write-once**: files land there during T2 with a manifest
(source URL, date, license, SHA-256 per file), and are never modified after.
A gate script re-hashes `raw/` at T8 and fails the pipeline on any mismatch.

## Alternatives considered

- **Mutable raw with version control:** relies on VCS to catch edits; works for
  small files but conflates "the dataset" with "whatever is checked in now"
  and breaks the moment files exceed sane VCS size. Rejected as the mechanism
  (VCS remains a backstop, not the guarantee).
- **Content-addressed store (DVC / git-annex):** the right tool past ~1GB, but
  pure overhead at this scale. Deferred — adopt if data outgrows the working tree.
- **No enforcement (convention only):** one careless script run destroys the
  trust anchor. Rejected.

## Consequences

- (+) Provenance has a verifiable root; any derived file can be challenged
  ("re-derive it from raw") and the challenge is executable.
- (+) Cheap: one manifest + one hash-check script.
- (−) Legitimate re-ingestion (new source version) must go through a new
  manifest + explicit re-derivation — mild friction, by design.
