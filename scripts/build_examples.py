"""Build tiny committed example slices mirroring the full data chain.

Samples 3 Opus + 2 iCliniq conversations (seed 42) and writes the same
records through every stage: raw -> structured -> atomic -> triaged.
Linkage is VERIFIED, not assumed: each raw row is checked against the
conversation's source_id before writing. Re-running reproduces byte-
identical output.

Usage:  D:\\anaconda3\\python.exe scripts/build_examples.py
"""
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "examples"
SEED = 42
N_OPUS, N_ICLINIQ = 3, 2


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    rng = random.Random(SEED)
    convs = load_jsonl(ROOT / "data/processed/conversations.jsonl")
    by_id = {c["conversation_id"]: c for c in convs}
    opus_ids = sorted(c["conversation_id"] for c in convs if c["source_id"].startswith("opus:"))
    icl_ids = sorted(c["conversation_id"] for c in convs if c["source_id"].startswith("icliniq:"))
    picked = rng.sample(opus_ids, N_OPUS) + rng.sample(icl_ids, N_ICLINIQ)
    print("picked:", [(by_id[i]["source_id"], i) for i in picked])

    raw_opus = load_jsonl(ROOT / "data/raw/opusdiseaseconversations.jsonl")
    raw_icl = json.loads((ROOT / "data/raw/iCliniq.json").read_text(encoding="utf-8"))

    raw_opus_out, raw_icl_out, conv_out = [], [], []
    for cid in picked:
        c = by_id[cid]
        conv_out.append(c)
        src = c["source_id"]
        if src.startswith("opus:"):
            _, disease, idx = src.split(":")
            row = raw_opus[int(idx)]
            assert row.get("name") == disease or row.get("source_disease") == disease, src
            raw_opus_out.append(row)
        else:
            idx = int(src.split(":")[1])
            row = raw_icl[idx]
            first_patient = next(t["text"] for t in c["turns"] if t["role"] == "patient")
            assert row["input"][:50] == first_patient[:50], src
            raw_icl_out.append(row)

    atomic = [json.loads(l) for l in open(ROOT / "data/processed/atomic.jsonl", encoding="utf-8")]
    kids = [a for a in atomic if a["conversation_id"] in set(picked)]
    want = {a["example_id"] for a in kids}
    triaged = [json.loads(l) for l in open(ROOT / "data/processed/triaged.jsonl", encoding="utf-8")]
    tri = [t for t in triaged if t["example_id"] in want]
    assert len(tri) == len(kids) and all(t["metadata"]["triage"] for t in tri)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "raw_opus_sample.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in raw_opus_out), encoding="utf-8")
    (OUT / "raw_icliniq_sample.json").write_text(
        json.dumps(raw_icl_out, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "conversations_sample.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in conv_out), encoding="utf-8")
    (OUT / "atomic_sample.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kids), encoding="utf-8")
    (OUT / "triaged_sample.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in tri), encoding="utf-8")
    verdicts = {}
    for t in tri:
        v = t["metadata"]["triage"]["verdict"]
        verdicts[v] = verdicts.get(v, 0) + 1
    (OUT / "README.md").write_text(
        "# Committed example slices\n\n"
        "Tiny verbatim excerpts of the real stores (full text, untruncated) so anyone\n"
        "browsing GitHub — or clicking the Archify pipeline diagram — can see actual\n"
        "data shapes without downloading ~500MB. Regenerate byte-identically with:\n\n"
        "    python scripts/build_examples.py\n\n"
        f"Provenance: seed {SEED}, {N_OPUS} Opus + {N_ICLINIQ} iCliniq conversations,\n"
        "raw rows verified against each conversation's source_id before writing.\n\n"
        "| file | rows | mirrors |\n"
        "|---|---|---|\n"
        f"| raw_opus_sample.jsonl | {len(raw_opus_out)} | data/raw/opusdiseaseconversations.jsonl |\n"
        f"| raw_icliniq_sample.json | {len(raw_icl_out)} | data/raw/iCliniq.json (same array container) |\n"
        f"| conversations_sample.jsonl | {len(conv_out)} | data/processed/conversations.jsonl |\n"
        f"| atomic_sample.jsonl | {len(kids)} | data/processed/atomic.jsonl |\n"
        f"| triaged_sample.jsonl | {len(tri)} | data/processed/triaged.jsonl |\n\n"
        f"Sample verdicts: {verdicts} (illustrative only, not the 18K/19K/8 census).\n\n"
        "Terms: Opus rows are MIT; iCliniq rows inherit academic-use-only terms.\n",
        encoding="utf-8")
    total = sum(p.stat().st_size for p in OUT.iterdir())
    print(f"wrote {len(kids)} atomic / {len(tri)} triaged rows, {total/1024:.1f} KB total in {OUT}")


if __name__ == "__main__":
    main()
