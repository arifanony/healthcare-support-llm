"""Validate the T4 atomic store (gate: check-atomic).

Covers AC-T4-1 (exactly one parent per record) and AC-T4-2 (turn-span
coverage report); AC-T4-3 (human spot-check of 50) is a manual review step:
  - every atomic.jsonl line validates against atomic/v1
  - example_id recomputed from source_id+span+version matches
  - conversation_id exists; source_id/context/message/response match the
    parent turns at the recorded span
  - ids unique; manifest entry hash/rows match
  - coverage report printed; re-run into temp dir is byte-identical
"""

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from curation.extract import ACTIONS, build, eligible_spans, example_id, format_context  # noqa: E402

EXAMPLE_ID = re.compile(r"^e-[0-9a-f]{16}$")
SPAN = re.compile(r"span=(\d+)")


def main():
    proc_dir = os.path.realpath(os.path.join(ROOT, "data", "processed"))
    errors = []
    manifest = json.load(open(os.path.join(proc_dir, "MANIFEST.json"), encoding="utf-8"))
    entries = {e["path"]: e for e in manifest.get("files", [])}
    entry = entries.get("atomic.jsonl")
    atomic_path = os.path.join(proc_dir, "atomic.jsonl")
    if entry is None or not os.path.isfile(atomic_path):
        print("atomic.jsonl missing from store or manifest", file=sys.stderr)
        return 1
    digest = hashlib.sha256()
    with open(atomic_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    if digest.hexdigest() != entry.get("sha256"):
        errors.append("atomic.jsonl: SHA-256 mismatch vs manifest")
    parents = {}
    with open(os.path.join(proc_dir, "conversations.jsonl"), encoding="utf-8") as f:
        for line in f:
            if line.strip():
                obj = json.loads(line)
                parents[obj["conversation_id"]] = obj
    seen_ids, seen_spans = set(), {}
    n_conv_parent = 0
    with open(atomic_path, encoding="utf-8") as f:
        atomic = [json.loads(line) for line in f if line.strip()]
    if len(atomic) != entry.get("rows"):
        errors.append(f"atomic rows {len(atomic)} != manifest {entry.get('rows')}")
    for obj in atomic:
        eid = obj.get("example_id", "?")
        if obj.get("schema_version") != "atomic/v1":
            errors.append(f"{eid}: bad schema_version")
            continue
        if not isinstance(eid, str) or not EXAMPLE_ID.match(eid):
            errors.append(f"{eid}: bad example_id")
        if eid in seen_ids:
            errors.append(f"{eid}: duplicate example_id")
        seen_ids.add(eid)
        parent = parents.get(obj.get("conversation_id"))
        if parent is None:  # AC-T4-1
            errors.append(f"{eid}: parent conversation missing")
            continue
        n_conv_parent += 1
        if obj.get("source_id") != parent["source_id"]:
            errors.append(f"{eid}: source_id != parent source_id")
        hist = obj.get("history") or []
        m = SPAN.search((hist[0].get("detail", "") if hist else ""))
        if not hist or hist[0].get("stage") != "T4" or not m:
            errors.append(f"{eid}: missing T4 span history")
            continue
        span = int(m.group(1))
        turns = parent["turns"]
        if not (0 <= span < len(turns) - 1):
            errors.append(f"{eid}: span {span} out of range")
            continue
        if turns[span]["role"] != "patient" or turns[span + 1]["role"] != "doctor":
            errors.append(f"{eid}: span {span} is not patient->doctor")
            continue
        if obj.get("user_message") != turns[span]["text"]:
            errors.append(f"{eid}: user_message != parent turn")
        if obj.get("response") != turns[span + 1]["text"]:
            errors.append(f"{eid}: response != parent turn")
        if obj.get("context") != format_context(turns[:span]):
            errors.append(f"{eid}: context != parent prior turns")
        if obj.get("example_id") != example_id(obj["source_id"], span):
            errors.append(f"{eid}: example_id not deterministic")
        if obj.get("action") not in ACTIONS:
            errors.append(f"{eid}: bad action {obj.get('action')!r}")
        meta = obj.get("metadata") or {}
        want_meta = {"quality": "unreviewed", "review_status": "pending",
                     "reviewer": None, "reviewed_at": None, "triage": None,
                     "safety_flags": [], "negative_reason": None}
        if any(meta.get(k) != v for k, v in want_meta.items()):
            errors.append(f"{eid}: metadata not in pre-triage state")
        seen_spans.setdefault(obj["conversation_id"], set()).add(span)
    # coverage (AC-T4-2): every eligible span extracted, turn coverage reported
    total_turns, covered_turns, convs_full = 0, 0, 0
    for cid, parent in parents.items():
        want = set(eligible_spans(parent["turns"]))
        got = seen_spans.get(cid, set())
        if want != got:
            errors.append(f"{cid}: spans extracted {sorted(got)} != eligible {sorted(want)}")
        else:
            convs_full += 1
        total_turns += len(parent["turns"])
        covered = set()
        for s in got:
            covered.update(range(0, s + 2))
        covered_turns += len(covered & set(range(len(parent["turns"]))))
    print(f"coverage: {convs_full}/{len(parents)} conversations fully extracted; "
          f"{covered_turns}/{total_turns} turns represented "
          f"({100.0 * covered_turns / max(total_turns, 1):.1f}%)")
    # determinism: rebuild in temp from the pre-T4 manifest, byte-compare
    if not errors:
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(os.path.join(proc_dir, "conversations.jsonl"), tmp)
            base = dict(manifest)
            base["files"] = [e for e in manifest["files"] if e["path"] != "atomic.jsonl"]
            base["producer"] = base["producer"].replace("+script:curation/extract.py", "")
            with open(os.path.join(tmp, "MANIFEST.json"), "w", encoding="utf-8") as f:
                json.dump(base, f, indent=2)
                f.write("\n")
            build(tmp)
            for name in ("atomic.jsonl", "MANIFEST.json"):
                want = open(os.path.join(proc_dir, name), "rb").read()
                got = open(os.path.join(tmp, name), "rb").read()
                if want != got:
                    errors.append(f"{name}: re-run not byte-identical")
    if errors:
        print("\n".join(errors[:20]), file=sys.stderr)
        if len(errors) > 20:
            print(f"... +{len(errors) - 20} more", file=sys.stderr)
        return 1
    print(f"atomic store OK: {len(atomic)} examples, {n_conv_parent} parent-linked, "
          f"determinism verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
