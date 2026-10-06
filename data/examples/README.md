# Committed example slices

Tiny verbatim excerpts of the real stores (full text, untruncated) so anyone
browsing GitHub — or clicking the Archify pipeline diagram — can see actual
data shapes without downloading ~500MB. Regenerate byte-identically with:

    python scripts/build_examples.py

Provenance: seed 42, 3 Opus + 2 iCliniq conversations,
raw rows verified against each conversation's source_id before writing.

| file | rows | mirrors |
|---|---|---|
| raw_opus_sample.jsonl | 3 | data/raw/opusdiseaseconversations.jsonl |
| raw_icliniq_sample.json | 2 | data/raw/iCliniq.json (same array container) |
| conversations_sample.jsonl | 5 | data/processed/conversations.jsonl |
| atomic_sample.jsonl | 48 | data/processed/atomic.jsonl |
| triaged_sample.jsonl | 48 | data/processed/triaged.jsonl |

Sample verdicts: {'REVIEW': 19, 'ACCEPT': 29} (illustrative only, not the 18K/19K/8 census).

Terms: Opus rows are MIT; iCliniq rows inherit academic-use-only terms.
