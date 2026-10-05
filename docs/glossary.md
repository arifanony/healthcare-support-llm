# Glossary

**Status:** draft for human approval · **Date:** 2026-09-29

| Term | Meaning in this project |
|---|---|
| SLM | Small Language Model (here: 1–4B parameters, instruction-tuned). |
| Atomic example | One decision-point record: history + patient message + action + target response. |
| Action label | The conversational behavior an example teaches (e.g. `ask_clarifying_question`). Closed vocabulary, see data contract §5. |
| Triage | Automated LLM grading of atomic examples into ACCEPT / REVIEW / REJECT. Advisory only. |
| Curation | Triage + human review + store assignment (T5–T7). |
| Curated store | Human-approved examples cleared for training. |
| Negative store | Rejected examples kept with reason codes; never in SFT. |
| Golden set | Locked, human-approved eval set. Never trained on. Versioned (`g1`, …). |
| Provenance | The unbroken record chain raw → … → curated/split for every example. |
| Manifest | Per-store JSON of file hashes, row counts, producer, config hash. |
| Split integrity | Guarantee that no conversation (or near-duplicate) spans train/val/golden. |
| Job spec | Declarative YAML describing one training run; the local↔GPU contract. |
| Adapter | LoRA/QLoRA weights; the only trained artifact stored per run. |
| Baseline | Base-model scores on golden, locked before fine-tuning. |
| SFT | Supervised fine-tuning (next-token training on curated examples). |
| DPO | Direct Preference Optimization — deferred future use for negative pairs. |
| Genesis | The state-management/verification layer tracking stages, tasks, and gates. |
| Gate | An executable check (or human approval) required for a stage transition. |
| Run record | `experiments/<run-id>/`: job spec copy, metrics, logs, notes. |
