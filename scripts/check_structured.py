"""Validate the T3 normalized store (gate: check-structured).

Covers AC-T3-1 (100% mapped or quarantined), AC-T3-2 (schema valid),
AC-T3-3 (byte-identical re-run):
  - processed MANIFEST present, hashes and row counts match
  - every conversations.jsonl line validates against conversation/v1
  - every quarantine.jsonl line carries a closed-vocab reason
  - ids unique; mapped + quarantined == raw MANIFEST rows, per file
  - re-running the producer into a temp dir is byte-identical
"""

import hashlib
import json
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from structuring.normalize import QUARANTINE_REASONS, build  # noqa: E402

CONV_ID = re.compile(r"^c-[0-9a-f]{16}$")
PREFIX_TO_FILE = {
    "opus": "opusdiseaseconversations.jsonl",
    "icliniq": "iCliniq.json",
}


def fail(errors, msg):
    errors.append(msg)


def check_manifest(proc_dir, errors):
    path = os.path.join(proc_dir, "MANIFEST.json")
    if not os.path.isfile(path):
        return fail(errors, "missing MANIFEST.json"), None
    manifest = json.load(open(path, encoding="utf-8"))
    if manifest.get("store") != "processed" or not manifest.get("files"):
        fail(errors, "manifest is not a processed-store manifest")
        return None, None
    for entry in manifest["files"]:
        p = os.path.join(proc_dir, entry.get("path", ""))
        if not os.path.isfile(p):
            fail(errors, f"{entry.get('path')}: file missing")
            continue
        digest = hashlib.sha256()
        rows = 0
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                digest.update(chunk)
                rows += chunk.count(b"\n")
        if digest.hexdigest() != entry.get("sha256"):
            fail(errors, f"{entry.get('path')}: SHA-256 mismatch")
        if rows != entry.get("rows"):
            fail(errors, f"{entry.get('path')}: rows {rows} != manifest {entry.get('rows')}")
    return None, manifest


def check_conversation(obj, errors):
    sid = obj.get("source_id", "?")
    if obj.get("schema_version") != "conversation/v1":
        return fail(errors, f"{sid}: bad schema_version")
    if not isinstance(obj.get("conversation_id"), str) or not CONV_ID.match(obj["conversation_id"]):
        fail(errors, f"{sid}: bad conversation_id")
    turns = obj.get("turns")
    if not isinstance(turns, list) or not turns:
        return fail(errors, f"{sid}: turns empty")
    prev = None
    for t in turns:
        if t.get("role") not in ("patient", "doctor"):
            return fail(errors, f"{sid}: bad role {t.get('role')!r}")
        if not isinstance(t.get("text"), str) or not t["text"].strip():
            return fail(errors, f"{sid}: empty turn text")
        if t["role"] == prev:
            return fail(errors, f"{sid}: non-alternating turns")
        prev = t["role"]
    meta = obj.get("meta") or {}
    if meta.get("quarantined") is not False or meta.get("quarantine_reason") is not None:
        fail(errors, f"{sid}: quarantined record in conversations file")
    hist = obj.get("history") or []
    if not any(h.get("stage") == "T3" and h.get("action") == "normalize" for h in hist):
        fail(errors, f"{sid}: missing T3 history entry")


def main():
    proc_dir = os.path.realpath(os.path.join(ROOT, "data", "processed"))
    errors = []
    _, manifest = check_manifest(proc_dir, errors)
    convs, quars = [], []
    conv_path = os.path.join(proc_dir, "conversations.jsonl")
    quar_path = os.path.join(proc_dir, "quarantine.jsonl")
    if manifest is not None:
        for path, coll in ((conv_path, convs), (quar_path, quars)):
            if not os.path.isfile(path):
                fail(errors, f"missing {os.path.basename(path)}")
                continue
            with open(path, encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if not line.strip():
                        continue
                    try:
                        coll.append(json.loads(line))
                    except json.JSONDecodeError:
                        fail(errors, f"{os.path.basename(path)} line {i}: invalid JSON")
        for obj in convs:
            check_conversation(obj, errors)
        for obj in quars:
            if not obj.get("source_id"):
                fail(errors, "quarantine record without source_id")
            if obj.get("reason") not in QUARANTINE_REASONS:
                fail(errors, f"{obj.get('source_id', '?')}: bad reason {obj.get('reason')!r}")
        # uniqueness (AC-T3-1: no double-processing, no drops)
        cids = [o.get("conversation_id") for o in convs]
        if len(set(cids)) != len(cids):
            fail(errors, "duplicate conversation_id")
        sids = [o.get("source_id") for o in convs] + [o.get("source_id") for o in quars]
        if len(set(sids)) != len(sids):
            fail(errors, "duplicate source_id across conversations + quarantine")
        # coverage against raw manifest, per file (AC-T3-1)
        raw_manifest = json.load(open(
            os.path.join(ROOT, "data", "raw", "MANIFEST.json"), encoding="utf-8"))
        raw_rows = {e["path"]: e["rows"] for e in raw_manifest["files"]}
        got = {name: 0 for name in raw_rows}
        for sid in sids:
            prefix = (sid or "").split(":")[0]
            name = PREFIX_TO_FILE.get(prefix)
            if name in got:
                got[name] += 1
            else:
                fail(errors, f"{sid}: unknown source prefix")
        for name, want in raw_rows.items():
            if got[name] != want:
                fail(errors, f"{name}: mapped {got[name]} != raw rows {want}")
    # determinism (AC-T3-3): byte-identical re-run
    if not errors:
        with tempfile.TemporaryDirectory() as tmp:
            build(tmp)
            for name in ("conversations.jsonl", "quarantine.jsonl", "MANIFEST.json"):
                with open(os.path.join(proc_dir, name), "rb") as f:
                    want = f.read()
                with open(os.path.join(tmp, name), "rb") as f:
                    got_bytes = f.read()
                if want != got_bytes:
                    fail(errors, f"{name}: re-run not byte-identical")
    if errors:
        print("\n".join(errors[:20]), file=sys.stderr)
        if len(errors) > 20:
            print(f"... +{len(errors) - 20} more", file=sys.stderr)
        return 1
    print(f"structured store OK: {len(convs)} conversations, {len(quars)} quarantined, "
          f"coverage + determinism verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
