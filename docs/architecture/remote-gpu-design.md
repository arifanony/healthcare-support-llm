# Remote GPU Design

**Status:** draft for human approval · **Stage:** T1/SPEC-1 · **Date:** 2026-09-29

How training executes off-machine while the repository stays the source of
truth. Companion ADR: [ADR-0010](../decisions/ADR-0010-colab-gpu-execution.md);
environment context: [environment-design.md](environment-design.md) §4–5.

## 1. Principle

The GPU backend is a **remote executor**, not a development environment.
It receives a declarative job spec + data, returns artifacts, and holds no
project state. Swapping backends changes one config block, never the pipeline.

## 2. Job lifecycle

```text
DEFINE (local)    job.yaml: datasets+hashes, base model, hyperparams, seed,
                  script commit pin, backend type, expected outputs
APPROVE (human)   spec approved before any GPU spend; recorded in run record
PROVISION         create runtime → detect GPU → install pinned deps →
                  verify dataset hashes
EXECUTE           run training script at pinned commit; checkpoint every N steps
COLLECT           adapter + tokenizer + metrics.json + logs → hash-verify →
                  artifacts/<run-id>/ + experiments/<run-id>/ record
TERMINATE         release runtime; record outcome (success / failed / interrupted)
```

Each attempt is recorded (`attempts: [{started, ended, reason, resumed_from}]`);
a disconnected session relaunches with `resumed_from` set — never a silent restart.

## 3. Runtime operations (backend interface)

Any backend must support these concepts (manual in v1, API-driven later):

| Operation | v1 (manual Colab) | Future (CLI/API) |
|---|---|---|
| create runtime | open notebook, select GPU | `colab runtime create --gpu t4` (or equiv.) |
| detect GPU | `nvidia-smi` cell | probe step in launcher, recorded |
| install deps | pinned `pip install` cell | spec `dependencies` block |
| execute script | clone repo at pin, run `src/training/train.py` | launcher pushes spec, polls status |
| save checkpoints | Drive mount / periodic download | artifact sync per checkpoint |
| save metrics/logs | download at end | streamed or pulled on completion |
| retrieve artifacts | manual download + local hash check | verified pull into `artifacts/` |
| terminate | close runtime / factory reset | launcher teardown |
| report | human pastes outcome into run record | exit receipt → run record |

## 4. Backend options

| Backend | Cost | Pros | Cons |
|---|---|---|---|
| Google Colab (free) | free | zero setup; T4-class GPU | timeouts, queues, no SLA; manual transfer |
| Google Colab (pay-as-you-go) | low | better GPUs, longer runtimes | cost; still manual in v1 |
| Kaggle GPU | free | weekly quota; API exists | quota limits; different environment |
| Local GPU / cloud VM | varies | full control, automatable | cost/setup before value is proven |

**v1:** Colab free tier, manual transfer. Fallback chain on inadequacy:
smaller model → QLoRA-4bit + accumulation → Kaggle → paid Colab (human decides).

## 5. Colab CLI investigation (future execution mechanism)

Where practical, evaluate Google's official Colab tooling / API surface as the
future launcher transport (create → execute → fetch → terminate without
browser interaction). v1 does not depend on it: the job-spec contract is the
stable interface, and the current manual path validates that contract before
any automation is built. Findings and the automation decision belong to a T10
runbook update, not to this phase.

## 6. Trust boundaries (recap)

- The backend never edits repo state, picks data, or tunes hyperparameters.
- Golden data never leaves local control except as inference prompts whose
  outputs are recorded (decided at T11; scoring stays local).
- No secrets in the job spec; gated-model tokens are human-entered in-session.
- Hash verification on both ends: backend verifies inputs, local verifies
  returned artifacts.
