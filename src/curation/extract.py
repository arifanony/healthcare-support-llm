"""Extract atomic decision-point examples (T4 curation).

Reads data/processed/conversations.jsonl, writes data/processed/atomic.jsonl:
one example per patient turn that is immediately followed by a doctor turn.
Appends the atomic.jsonl entry to the processed MANIFEST (idempotent).

example_id = "e-" + sha256(source_id|span|atomic/v1)[:16] (data-arch §2).
context = all prior turns formatted "role: text" ("" when none).
action = PROVISIONAL rule-based label (ordered rules, first match wins);
T5/human refines it. Rules lean safe: emergency and redirect language maps
to advise_professional_evaluation.

Note: after T4 runs, the T3 gate's manifest byte-comparison legitimately
fails (store evolved); in-order re-execution (T3 producer -> T3 gate ->
T4 producer -> T4 gate) stays green.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

ACTIONS = (
    "answer",
    "ask_clarifying_question",
    "acknowledge",
    "provide_general_information",
    "request_more_context",
    "advise_professional_evaluation",
    "refuse_unsafe_request",
    "respond_cautiously",
)

EMERGENCY = (
    "chest pain", "can't breathe", "cannot breathe", "difficulty breathing",
    "shortness of breath", "bleeding heavily", "heavy bleeding", "suicide",
    "kill myself", "end my life", "overdose", "stroke", "heart attack",
    "unconscious", "passed out", "anaphylaxis", "throat closing",
    "severe head", "seizure", "convulsion", "poisoning", "stabbed",
    "gunshot", "severe burn", "choking",
)

REDIRECT = (
    "cannot diagnose", "can't diagnose", "unable to diagnose",
    "see a doctor", "consult a doctor", "consult a ", "consult an ",
    "consult your", "see your doctor", "talk to your doctor", "in person",
    "emergency room", "emergency department", "call emergency",
    "not a medical professional", "not medical advice",
)

RECORD_WORDS = (
    "report", "reports", "result", "results", "history", "medication",
    "medications", "medicine", "medicines", "test", "tests", "lab", "labs",
    "scan", "scans", "x-ray", "xray", "mri", "prescription", "records",
)

GREETING = re.compile(
    r"^(hi|hello|hey|good morning|good afternoon|good evening|thank|thanks|"
    r"you'?re welcome|welcome)\b"
)


def provisional_action(patient_msg, doctor_resp):
    """Ordered rules -> (action, rule_id). Provisional; T5/human refines."""
    p, r = patient_msg.casefold(), doctor_resp.casefold()
    if any(e in p for e in EMERGENCY):
        return "advise_professional_evaluation", "emergency_lexicon"
    if any(d in r for d in REDIRECT):
        return "advise_professional_evaluation", "redirect"
    if len(r) < 200 and GREETING.match(r.strip()):
        return "acknowledge", "greeting"
    questions = r.count("?")
    if questions >= 1 and questions > r.count(".") + r.count("!"):
        if any(w in r for w in RECORD_WORDS):
            return "request_more_context", "records_question"
        return "ask_clarifying_question", "clarifying_question"
    if "general information" in r or "in general" in r:
        return "provide_general_information", "general_info"
    return "answer", "default"


def example_id(source_id, span):
    raw = f"{source_id}|{span}|atomic/v1"
    return "e-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def format_context(turns):
    return "\n".join(f"{t['role']}: {t['text']}" for t in turns)


def eligible_spans(turns):
    return [i for i in range(len(turns) - 1)
            if turns[i]["role"] == "patient" and turns[i + 1]["role"] == "doctor"]


def extract_conversation(conv, timestamp):
    examples = []
    turns = conv["turns"]
    for span in eligible_spans(turns):
        patient_msg = turns[span]["text"]
        response = turns[span + 1]["text"]
        action, rule = provisional_action(patient_msg, response)
        examples.append({
            "schema_version": "atomic/v1",
            "example_id": example_id(conv["source_id"], span),
            "conversation_id": conv["conversation_id"],
            "source_id": conv["source_id"],
            "context": format_context(turns[:span]),
            "user_message": patient_msg,
            "action": action,
            "response": response,
            "metadata": {
                "quality": "unreviewed",
                "review_status": "pending",
                "reviewer": None,
                "reviewed_at": None,
                "triage": None,
                "safety_flags": [],
                "negative_reason": None,
            },
            "history": [{
                "stage": "T4", "action": "extract",
                "actor": "script:curation/extract.py",
                "timestamp": timestamp,
                "detail": f"span={span} rule={rule}",
            }],
        })
    return examples


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(proc_dir):
    with open(os.path.join(proc_dir, "MANIFEST.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    timestamp = manifest["created_at"]
    examples = []
    with open(os.path.join(proc_dir, "conversations.jsonl"), encoding="utf-8") as f:
        for line in f:
            if line.strip():
                examples.extend(extract_conversation(json.loads(line), timestamp))
    atomic_path = os.path.join(proc_dir, "atomic.jsonl")
    with open(atomic_path, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")
    manifest["files"] = [e for e in manifest["files"] if e["path"] != "atomic.jsonl"]
    manifest["files"].append({
        "path": "atomic.jsonl", "sha256": sha256_of(atomic_path), "rows": len(examples),
    })
    if "curation/extract.py" not in manifest.get("producer", ""):
        manifest["producer"] += "+script:curation/extract.py"
    with open(os.path.join(proc_dir, "MANIFEST.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    actions = Counter(ex["action"] for ex in examples)
    return len(examples), actions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=os.path.join(ROOT, "data", "processed"))
    args = parser.parse_args()
    n, actions = build(os.path.realpath(args.dir))
    print(f"extracted {n} atomic examples -> {args.dir}")
    for action, count in actions.most_common():
        print(f"  {action}: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
