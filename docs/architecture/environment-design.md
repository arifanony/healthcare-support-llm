# Environment Design

**Status:** draft for human approval · **Stage:** T1 · **Date:** 2026-09-29

Where each part of the project lives and how artifacts move between
environments. Principle: **project logic lives in this repo; the GPU backend
is a remote executor, nothing more.**

## 1. Local environment (primary)

- **OS/tooling:** Windows host, VS Code, coding agent (this session's role),
  Git/Mercurial for version control, Python 3.11+ (see §4).
- **Owns:** all source (`src/`), configs, docs, datasets, review work,
  splitting, evaluation scoring, experiment records.
- **Runs:** T1–T9, T11 scoring/comparison, T12 — everything except GPU training
  and (optionally) LLM-as-judge inference at scale.

## 2. Coding-agent environment (this harness)

- The agent edits repo files, runs local scripts/tests, and prepares GPU job
  specs — but never launches GPU spend, downloads datasets, or approves gates
  without explicit human instruction.
- Sandboxed execution (as in this session) may not reach the network or host
  tools like Genesis — those steps are marked human-run in each stage plan.

## 3. Python environment

- One virtualenv per developer machine, rooted at the repo (`.venv/`),
  managed by `uv`: `uv sync` reproduces it from the checked-in
  `pyproject.toml` + `uv.lock` (see ADR-0012). Dependencies stay minimal
  and stdlib-first; data libs are added at T2, when the dependency set is
  known (`datasets`, `pandas`/`pyarrow` candidates; ML libs only where needed).
- Stdlib-first for pipeline code (hashing, JSONL, argparse); heavy deps
  (`torch`, `transformers`, `peft`, `unsloth`) are **GPU-backend-only** in v1 — the local
  env must be able to run T2–T9 and T11-scoring without them. Local eval
  *generation* (running the model to produce responses) happens on the GPU
  backend or via the base-model API; local code scores recorded outputs.
- Reproducibility: the committed `uv.lock` pins every local env; a
  `uv pip freeze` snapshot is stored per experiment that involves
  local execution.

## 4. GPU execution environment (remote, later)

Target: Google Colab (free tier first); fallback: Kaggle GPU, then paid Colab.
The backend provides, per job:

1. GPU runtime (T4-class or better) for the job's duration.
2. Dependency install from a pinned list in the job spec.
3. Execution of the training script **from this repo at a pinned commit**.
4. Checkpointing to survive disconnects (resume-from-last-checkpoint).
5. Export: adapter weights, tokenizer, `metrics.json`, full logs.

What the backend never does: edit repo state, pick data, choose
hyperparameters, or evaluate on golden (golden stays local; eval generation
for golden prompts may run remotely only as recorded-output production, with
scoring local — decided at T11).

Session-failure handling (see also ADR-0010):

- checkpoints every N steps to mounted Drive / downloaded artifacts;
- the job spec records `attempts: [{started, ended, reason, resumed_from}]`;
- a disconnected session is a recorded event, not a lost run — relaunch with
  `resumed_from` set, never silently restart.

## 5. Artifact movement

```text
LOCAL ──► BACKEND : job spec (YAML) + train/val .jsonl + script pin (commit hash)
BACKEND ──► LOCAL : adapter (*.safetensors) + tokenizer/ + metrics.json + *.log
LOCAL STORAGE     : artifacts/<run-id>/ (git-ignored) + experiments/<run-id>/ (checked in: spec, metrics, notes — never weights)
```

Transfer mechanism v1: manual upload/download via the Colab UI + Drive.
Automation (API-driven launch, artifact pull) is an explicitly deferred
future — the job-spec contract is designed so automation can adopt it later
without changing the interface.

## 6. Data locality and secrets

- Datasets are small (MBs) — full copies live in the repo working tree;
  large-file tooling (Git LFS / DVC) deferred until artifacts exceed sane
  clone size.
- No credentials in the repo. The GPU backend holds no secrets beyond the
  session's own auth; Hugging Face gated-model tokens (if the base model needs
  one) are human-entered in the Colab session, never written to the job spec.

## 7. Future automation boundary

When (not now): a `src/training/launcher.py` + CI job could push specs and
pull artifacts programmatically. The boundary stays the same — local decides,
backend executes — only the transport becomes code instead of hands.
