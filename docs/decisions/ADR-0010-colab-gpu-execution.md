# ADR-0010 — Remote GPU / Google Colab architecture

**Status:** proposed — contract fixed, backend choice provisional (pending human approval) · **Date:** 2026-09-29 · **Stage:** T1

## Context

Training needs a GPU the local machine may lack; all project logic, data, and
judgment live in this repo. The GPU backend must be interchangeable and dumb.

## Problem

How do we execute training remotely without scattering project logic into
notebooks or coupling the pipeline to one provider?

## Decision

- The GPU backend is a **remote executor** behind a declarative **training job
  spec** (YAML: dataset hashes, base model, hyperparams, seed, script commit
  pin, expected outputs).
- Local prepares spec + data; backend provisions runtime, installs pinned
  deps, runs the repo's training script at the pinned commit, checkpoints
  defensively, and returns adapter + tokenizer + metrics + logs.
- Transfer in v1 is **manual** (Colab UI + Drive); the spec contract is shaped
  so API-driven launch/artifact-pull can adopt it later unchanged.
- Session failures are **recorded attempts** (`resumed_from` checkpoint), never
  silent restarts.

## Alternatives considered

- **Notebook-as-project (logic lives in Colab):** the classic failure mode —
  irreproducible cells, data choices buried in outputs, no versioning.
  Rejected emphatically.
- **Local GPU purchase / cloud VM now:** cost and setup before the experiment
  has proven worth it. Deferred — revisit if free-tier friction blocks T10.
- **Full automation now (API launch + artifact sync):** real engineering for a
  one-run v1; the manual path validates the contract first. Deferred, designed for.

## Consequences

- (+) Provider swap (Colab → Kaggle → paid) touches one config block, not the pipeline.
- (+) Every run is reproducible from the checked-in spec + hashed datasets.
- (−) Manual transfer is slow and human-error-prone; mitigated by hash checks
  on both ends (job spec records expected hashes; fetch verifies them).
- (−) Free-tier limits (timeouts, queueing) are accepted schedule risks with a
  documented fallback chain.

## Validation

Backend choice (Colab free vs alternatives) is provisional until the T10 VRAM
probe; the job-spec contract itself is final for v1.
