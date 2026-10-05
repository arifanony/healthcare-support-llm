"""Normalize raw sources to conversation/v1 (T3 structuring).

Reads data/raw/ (verified by the T2 manifest), writes to --out (default
data/processed/): conversations.jsonl, quarantine.jsonl, MANIFEST.json.

Mapping:
  opus jsonl   user->patient, assistant->doctor, system turns dropped
               (instruction leak, not dialogue); consecutive same-role turns
               merged with newline (standard ChatML normalization).
  icliniq json one patient turn (input) + one doctor turn (answer_icliniq,
               the real doctor answer); answer_chatgpt/answer_chatdoctor stay
               in raw, reachable via source_id.

Determinism (AC-T3-3): history/manifest timestamps reuse the raw manifest's
created_at, so re-runs are byte-identical. Unmappable rows go to
quarantine.jsonl with a closed-vocab reason, never silently dropped.
"""

import argparse
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
RAW_DIR = os.path.join(ROOT, "data", "raw")

QUARANTINE_REASONS = (
    "unparseable_row",
    "missing_field",
    "empty_conversation",
    "empty_turn_text",
    "unknown_role",
    "non_alternating_roles",
)

ROLE_MAP = {"user": "patient", "assistant": "doctor"}


def conversation_id(turns):
    text = "\n".join(f"{t['role']}:{t['text']}" for t in turns)
    return "c-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def normalize_turns(raw_turns):
    """Map roles, drop system turns, merge same-role runs. Returns (turns, dropped_system) or raises."""
    turns = []
    dropped_system = 0
    for t in raw_turns:
        role = t.get("role")
        if role == "system":
            dropped_system += 1
            continue
        if role not in ROLE_MAP:
            raise _Quarantine("unknown_role")
        text = (t.get("content") or "").strip()
        if not text:
            raise _Quarantine("empty_turn_text")
        mapped = ROLE_MAP[role]
        if turns and turns[-1]["role"] == mapped:
            turns[-1]["text"] += "\n" + text
        else:
            turns.append({"role": mapped, "text": text})
    if not turns:
        raise _Quarantine("empty_conversation")
    # Leading doctor turns (opening greeting + chart context) are kept:
    # the contract requires alternating non-empty turns, not a fixed opener.
    # T4 treats patient messages as decision points; leading doctor turns
    # are context only.
    return turns, dropped_system


class _Quarantine(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def record(source_id, turns, timestamp, detail):
    return {
        "schema_version": "conversation/v1",
        "conversation_id": conversation_id(turns),
        "source_id": source_id,
        "turns": turns,
        "meta": {"source_rows": 1, "quarantined": False, "quarantine_reason": None},
        "history": [{
            "stage": "T3", "action": "normalize",
            "actor": "script:structuring/normalize.py",
            "timestamp": timestamp, "detail": detail,
        }],
    }


def convert_opus(timestamp):
    convs, quar = [], []
    with open(os.path.join(RAW_DIR, "opusdiseaseconversations.jsonl"),
              encoding="utf-8", errors="replace") as f:
        lines = [(row, line) for row, line in enumerate(f) if line.strip()]
    for row, line in lines:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            quar.append(("opus:?:%d" % row, "unparseable_row", line[:200]))
            continue
        source_id = "opus:%s:%d" % (obj.get("name", "?"), row)
        raw_turns = obj.get("conversation")
        if not isinstance(raw_turns, list) or not raw_turns:
            quar.append((source_id, "missing_field" if raw_turns is None else "empty_conversation", line[:200]))
            continue
        try:
            turns, dropped = normalize_turns(raw_turns)
        except _Quarantine as q:
            quar.append((source_id, q.reason, line[:200]))
            continue
        detail = "opus chatml; dropped %d system turns; disease=%s icd10=%s" % (
            dropped, obj.get("name"), obj.get("icd10"))
        convs.append(record(source_id, turns, timestamp, detail))
    return convs, quar


def convert_icliniq(timestamp):
    convs, quar = [], []
    with open(os.path.join(RAW_DIR, "iCliniq.json"), encoding="utf-8", errors="replace") as f:
        data = json.load(f)
    for row, obj in enumerate(data):
        source_id = "icliniq:%d" % row
        question = (obj.get("input") or "").strip()
        answer = (obj.get("answer_icliniq") or "").strip()
        if not question or not answer:
            quar.append((source_id, "missing_field" if not question else "empty_turn_text", json.dumps(obj)[:200]))
            continue
        turns = [{"role": "patient", "text": question},
                 {"role": "doctor", "text": answer}]
        detail = "icliniq single-turn; primary=answer_icliniq; alternates in raw"
        convs.append(record(source_id, turns, timestamp, detail))
    return convs, quar


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(out_dir):
    with open(os.path.join(RAW_DIR, "MANIFEST.json"), encoding="utf-8") as f:
        raw_manifest = json.load(f)
    timestamp = raw_manifest["created_at"]
    os.makedirs(out_dir, exist_ok=True)
    convs, quar = [], []
    for converter in (convert_opus, convert_icliniq):
        c, q = converter(timestamp)
        convs.extend(c)
        quar.extend(q)
    outputs = {
        "conversations.jsonl": [json.dumps(c) for c in convs],
        "quarantine.jsonl": [
            json.dumps({"source_id": s, "reason": r, "excerpt": e}) for s, r, e in quar
        ],
    }
    files = []
    for name, lines in outputs.items():
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")
        files.append({"path": name, "sha256": sha256_of(path), "rows": len(lines)})
    manifest = {
        "store": "processed",
        "created_at": timestamp,
        "producer": "script:structuring/normalize.py",
        "files": files,
    }
    with open(os.path.join(out_dir, "MANIFEST.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    return len(convs), len(quar)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join(ROOT, "data", "processed"))
    args = parser.parse_args()
    convs, quar = build(os.path.realpath(args.out))
    print(f"normalized {convs} conversations, quarantined {quar} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
