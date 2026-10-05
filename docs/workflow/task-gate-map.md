# T1–T12 → Genesis task map (proposed, not yet live)

Authoritative stage contract: `docs/workflow/t1-t12-workflow.md`.
Each row becomes one `genesis task add` entry after adoption, with the listed
executable gate(s). States: `queued → pending → active → completed`
(`rejected`/`stale` on gate failure / upstream change).

| Task | Outcome | Proposed gate (script) | Human approval gate |
|---|---|---|---|
| T1 | docs + ADRs + diagrams approved | docs present (checklist) | plan/spec approval |
| T2 | `data/raw/` + manifest | `scripts/check_manifest.py data/raw` | license confirm |
| T3 | normalized conversations | schema-validate + determinism re-run | — |
| T4 | atomic examples | parent-link check + coverage report | 50-record spot-check |
| T5 | triage verdicts on 100% | verdict completeness + vocab check | 100-record calibration |
| T6 | human decisions merged | `human_approved` requires reviewer+ts | the review itself |
| T7 | curated + negative stores | `scripts/verify_provenance.py` | — |
| T8 | quality report + go/no-go | report exists; dedup resolved | go/no-go |
| T9 | splits + golden lock | `scripts/check_no_golden_leak.py` + determinism | golden lock sign |
| T10 | adapter + metrics + logs | artifacts hashed; loss sane | job-spec pre-approval |
| T11 | baseline + comparison | golden-hash equality; decoding diff | result accept/reject |
| T12 | error analysis + iteration proposal | note exists with falsifiable proposal | approve/close iteration |

Loop-backs: T8 no-go → T6/T4 `active`, T9–T12 `stale`; T12 approved iteration →
affected stages `stale`. Baseline T11a may run once T9 completes (no T10 dependency).
