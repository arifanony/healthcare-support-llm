"""Build data/raw/MANIFEST.json (T2 ingestion).

Hashes every data file in data/raw/, records provenance, row counts, and
sizes, then marks the data files read-only (write-once store).
Idempotent: re-running rebuilds the manifest from current bytes.
"""

import hashlib
import json
import os
import stat
import sys
from datetime import datetime, timezone

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
MANIFEST = os.path.join(RAW_DIR, "MANIFEST.json")

# Provenance recorded in Genesis (KNOWLEDGE-8c51c018, KNOWLEDGE-df84159e).
PROVENANCE = {
    "iCliniq.json": {
        "origin": "https://github.com/AbdelAbys/ChatDoctor "
                  "(mirror of Kent0n-Li/ChatDoctor; also HF lavita/ChatDoctor-iCliniq)",
        "retrieved_at": "2026-09-30",
        "license": "Apache-2.0 (code); academic-research-only, "
                   "non-commercial, non-clinical (data)",
    },
    "opusdiseaseconversations.jsonl": {
        "origin": "https://huggingface.co/datasets/"
                  "nisten/opus-doctor-patient-conversations-all-human-diseases",
        "retrieved_at": "2026-09-30",
        "license": "MIT",
    },
}


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_rows(path):
    if path.endswith(".jsonl"):
        with open(path, "rb") as f:
            return sum(1 for line in f if line.strip())
    if path.endswith(".json"):
        with open(path, encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        return len(data) if isinstance(data, list) else None
    return None


def main():
    raw_dir = os.path.realpath(RAW_DIR)
    names = sorted(
        n for n in os.listdir(raw_dir)
        if os.path.isfile(os.path.join(raw_dir, n)) and n != "MANIFEST.json"
    )
    if not names:
        print("no data files in data/raw/", file=sys.stderr)
        return 1
    unknown = [n for n in names if n not in PROVENANCE]
    if unknown:
        print(f"missing provenance for: {', '.join(unknown)}", file=sys.stderr)
        return 1
    files = []
    for name in names:
        path = os.path.join(raw_dir, name)
        files.append({
            "path": name,
            "sha256": sha256_of(path),
            "bytes": os.path.getsize(path),
            "rows": count_rows(path),
            **PROVENANCE[name],
        })
    manifest = {
        "store": "raw",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "producer": "script:build_manifest.py",
        "files": files,
    }
    with open(os.path.join(raw_dir, "MANIFEST.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    for name in names:  # AC-T2-3: write-once store (manifest itself stays writable)
        os.chmod(os.path.join(raw_dir, name), stat.S_IREAD)
    print(f"manifested {len(files)} files from {raw_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
