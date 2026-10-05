"""Verify data/raw/ against MANIFEST.json (T2 gate).

Fails on: missing manifest, missing/unlisted/extra files, hash mismatch,
or missing provenance fields (origin, retrieved_at, license).
"""

import hashlib
import json
import os
import sys

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
REQUIRED = ("path", "sha256", "rows", "bytes", "origin", "retrieved_at", "license")


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    raw_dir = os.path.realpath(RAW_DIR)
    manifest_path = os.path.join(raw_dir, "MANIFEST.json")
    if not os.path.isfile(manifest_path):
        print("missing data/raw/MANIFEST.json", file=sys.stderr)
        return 1
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    if manifest.get("store") != "raw" or not manifest.get("files"):
        print("manifest is not a raw-store manifest", file=sys.stderr)
        return 1
    errors = []
    listed = set()
    for entry in manifest["files"]:
        missing = [k for k in REQUIRED if entry.get(k) in (None, "")]
        if missing:
            errors.append(f"{entry.get('path', '?')}: missing {', '.join(missing)}")
            continue
        listed.add(entry["path"])
        path = os.path.join(raw_dir, entry["path"])
        if not os.path.isfile(path):
            errors.append(f"{entry['path']}: file missing")
        elif sha256_of(path) != entry["sha256"]:
            errors.append(f"{entry['path']}: SHA-256 mismatch (raw store mutated)")
    on_disk = {n for n in os.listdir(raw_dir)
               if os.path.isfile(os.path.join(raw_dir, n)) and n != "MANIFEST.json"}
    for extra in sorted(on_disk - listed):
        errors.append(f"{extra}: on disk but not in manifest")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"raw store OK: {len(listed)} files hash-verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
