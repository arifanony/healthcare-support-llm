# ADR-0012 — UV for Python packaging and environments

**Status:** approved (human-approved 2026-09-30) · **Date:** 2026-09-30 · **Stage:** T1

## Context

The T1 draft specified a hand-managed virtualenv built from a pinned
requirements file at T2, with `pip freeze` snapshots per experiment.
No packaging files exist yet, so the choice is still free.

## Problem

What tool owns the local Python environment and dependency lockfile?

## Decision

- **UV** owns both: `pyproject.toml` declares dependencies,
  `uv.lock` (checked in) pins them, `uv sync` reproduces `.venv/`.
- **Zero dependencies at scaffold time:** stdlib-first pipeline code
  needs nothing installed; data libs are added at T2 when the dataset
  choice (Q1) fixes the dependency set.
- **`[tool.uv] package = false`** until `src/` becomes a real importable
  package; no editable install of an empty tree.
- **Per-experiment record** stays equivalent to the old plan: the committed
  `uv.lock` plus `uv pip freeze` snapshots where a resolved-env record
  is needed.

## Alternatives considered

- **pip + requirements file (T1 draft):** no real lockfile, manual
  discipline, slower; superseded by this decision.
- **Poetry / PDM:** heavier workflow than v1 needs; uv covers
  venv + lock + run in one binary. Rejected.
- **conda:** unnecessary at this scale; no native non-Python deps in v1.
  Rejected.

## Consequences

- (+) One command (`uv sync`) reproduces the exact local env on any machine.
- (+) Lockfile satisfies NFR-4 (pinned deps) from day one.
- (+) `docs/architecture/environment-design.md` §3 updated to match.
- (−) Contributors need `uv` installed — single static binary, accepted.

## Validation

`uv sync --offline --locked` exits 0 on a clean checkout; `.venv/`
runs Python 3.11.
