"""Deterministic rules triage (T5 curation).

Reads data/processed/atomic.jsonl, writes data/processed/triaged.jsonl
(atomic/v1 records with metadata.triage filled, safety_flags set, and a T5
history entry), triage_report.json (distributions, model/prompt id, config
hash, calibration agreement), and calibration_sample.json (100 blind records
for the AC-T5-2 human calibration; written once, never overwritten).
Appends the triaged.jsonl + triage_report.json entries to the processed
MANIFEST (idempotent); the calibration sample stays unmanifested like
spotcheck_T4.md (it gains human grades after the build).

v1 is rules, not LLM: the agent sandbox has no network, and gates require
byte-identical re-runs, which an API model cannot promise. The rulepack is
the model (model id rules-triage/v1, rubric triage/v1); LLM triage is
deferred to a T12 iteration if calibration shows rules failing. Rules lean
safe: any dimension <=2 routes to REVIEW or REJECT (curation-strategy §2),
and only T6 moves records into stores. Dimensions rules cannot judge stay
near-neutral (plausibility 3, instruction_adherence 4) by design.

Note: after T5 runs, the T4 gate's manifest byte-comparison legitimately
fails (store evolved); in-order re-execution stays green (same pattern as
extract.py).
"""

import argparse
import copy
import json
import os
import random
import re
import sys

SRC = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, SRC)
from curation.extract import EMERGENCY, REDIRECT, sha256_of  # noqa: E402

ROOT = os.path.dirname(SRC)
CONFIG_PATH = os.path.join(ROOT, "configs", "triage.yaml")
REPORT_VERSION = "triage-report/v1"
SAMPLE_N = 100
SAMPLE_CTX_CHARS = 2000

VERDICTS = ("ACCEPT", "REVIEW", "REJECT")
SAFETY_FLAGS = (
    "none",
    "unvalidated_claim",
    "diagnosis_stated",
    "treatment_recommended",
    "dosage_mentioned",
    "emergency_signs_present",
    "disallowed_content",
    "pii_present",
)
NEGATIVE_REASONS = (
    "unsafe_response",
    "unsupported_diagnosis",
    "hallucination",
    "irrelevant_response",
    "insufficient_clarification",
    "overconfident_answer",
    "missing_important_context",
    "inappropriate_tone",
)
PATTERN_KEYS = (
    "dosage_pattern",
    "diagnosis_pattern",
    "treatment_pattern",
    "percent_pattern",
    "email_pattern",
    "phone_pattern",
)

TOKEN = re.compile(r"[a-z0-9]+")
STOP = set("a an the and or but if then so of to in on for with is are was "
           "were be been it its this that these those you your he she they "
           "we i my me him her them us our as at by from not no do does did "
           "have has had will would can could should there here what when "
           "where which who how why s t d ll m re ve don isn aren wasn "
           "weren haven hasn hadn wouldn couldn shouldn won".split())


def _scalar(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def load_config(path=CONFIG_PATH):
    """Minimal-subset YAML: comments, flat scalars, top-level scalar lists."""
    cfg, key = {}, None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.split("#", 1)[0].rstrip()
            if not line.strip():
                continue
            if line[0] in " \t":
                item = line.strip()
                if not item.startswith("- ") or key is None:
                    raise ValueError("bad list line: %r" % raw.strip())
                cfg[key].append(_scalar(item[2:]))
            else:
                name, sep, value = line.partition(":")
                if not sep:
                    raise ValueError("bad line: %r" % raw.strip())
                name, value = name.strip(), value.strip()
                if value == "":
                    cfg[name], key = [], name
                else:
                    cfg[name], key = _scalar(value), None
    return cfg


def compile_patterns(cfg):
    return {k: re.compile(cfg[k]) for k in PATTERN_KEYS}


def content_words(text):
    return set(TOKEN.findall(text.casefold())) - STOP


def recall(patient_msg, response):
    words = content_words(patient_msg)
    if not words:
        return 0.0
    return len(words & set(TOKEN.findall(response.casefold()))) / len(words)


CLAUSE_SPLIT = re.compile(r"[.!?;\n,:—–]+| - ")
FIRST_PERSON = re.compile(r"\b(i|me|my|mine|we|us|our)\b")


def _nearby(words, idx, terms, before, after):
    window = words[max(0, idx - before):idx + after]
    joined = " ".join(window)
    return any(t in window if " " not in t else t in joined for t in terms)


def _seq_index(tokens, phrase):
    """Token index where phrase starts, or -1 (word-exact, so "spend my
    life" never matches "end my life" and "yearly" never matches "year")."""
    need = TOKEN.findall(phrase)
    for i in range(len(tokens) + 1 - len(need)):
        if tokens[i:i + len(need)] == need:
            return i
    return -1


AUX_STRIP = re.compile(
    r"\b(tried to|try to|want to|going to|have to|has to|had to|able to)\b")


def emergency_level(patient_msg, cfg):
    """'acute' for a first-person present-tense emergency report, 'mention'
    for any other emergency-term mention, None when absent. Sentence-level:
    a term is acute only with a first-person report, no negation or
    non-acute markers nearby, no family-member context, and no educational
    opener. Compounds like "seizure medicine" never count."""
    family = re.compile(r"\bmy (?:%s)\b" % "|".join(cfg["family_terms"]))
    age = re.compile(r"\b\d+(?: years? old|[- ]year[- ]old)\b")
    base = age.sub(" ", patient_msg.casefold())
    btoks = TOKEN.findall(base)
    past = any(_seq_index(btoks, m) >= 0 for m in cfg["history_terms"])
    found = False
    for sent in CLAUSE_SPLIT.split(AUX_STRIP.sub(" ", base)):
        text = sent
        for compound in cfg["emergency_compounds"]:
            text = text.replace(compound, " ")
        opener = any(text.strip().startswith(op)
                     for op in cfg["educational_openers"])
        words = TOKEN.findall(text)
        chronic = any(_seq_index(words, t) >= 0
                      for t in cfg["nonacute_terms"])
        for term in EMERGENCY:
            if term == "suicide":
                continue  # owned by the self-harm path (mention-level)
            idx = text.find(term)
            if idx < 0:
                continue
            found = True
            if opener or chronic:
                continue
            at = len(TOKEN.findall(text[:idx]))
            if _nearby(words, at, cfg["negation_terms"], 4, 0):
                continue
            if (term == "severe head" and "ache" in "".join(words)
                    and not any(w in words for w in
                                ("injury", "trauma", "accident", "fall", "fell",
                                 "hit", "blow", "crash", "assault"))):
                continue  # severe headache is routine; head injury is not
            if any(pn in words[max(0, at - 4):at] for pn in
                   ("he", "she", "they", "him", "her", "them", "his", "their")):
                continue  # third-person subject, not the patient's own report
            if any(words[j] in ("say", "says", "said", "saying")
                   and (j == 0 or words[j - 1] != "i")
                   for j in range(max(0, at - 4), at)):
                continue  # reported speech, not a self-report
            if FIRST_PERSON.search(family.sub(" ", text)) is None:
                continue
            return "mention" if past else "acute"
    return "mention" if found else None


def selfharm_level(patient_msg, cfg):
    """'acute' for a first-person present-tense self-harm report or a
    third-person violence threat, 'mention' for vaguer references."""
    base = patient_msg.casefold()
    past = any(_seq_index(TOKEN.findall(base), m) >= 0
               for m in cfg["history_terms"])
    found = False
    for clause in CLAUSE_SPLIT.split(AUX_STRIP.sub(" ", base)):
        text = clause.strip()
        if not text:
            continue
        words = TOKEN.findall(text)
        for term in cfg["selfharm_acute_terms"]:
            at = _seq_index(words, term)
            if at < 0:
                continue
            found = True
            if _nearby(words, at, cfg["negation_terms"], 4, 0):
                continue
            if FIRST_PERSON.search(text) is None:
                continue
            return "mention" if past else "acute"
        for term in cfg["selfharm_other_terms"]:
            at = _seq_index(words, term)
            if at < 0:
                continue
            found = True
            if _nearby(words, at, cfg["negation_terms"], 4, 0):
                continue
            return "mention" if past else "acute"
        if any(_seq_index(words, term) >= 0
               for term in cfg["selfharm_mention_terms"]):
            found = True
    return "mention" if found else None


def toxic_language(response, cfg):
    for term in cfg["toxic_terms"]:
        idx = response.find(term)
        if idx < 0:
            continue
        words = TOKEN.findall(response[:idx])
        if any(neg in words[-5:] for neg in
               ("not", "no", "never", "none", "nothing", "far", "isn",
                "aren", "wasn", "weren", "don", "doesn", "didn")):
            continue  # reassurance ("far from an idiot") is not blame
        if any(rep in words[-5:] for rep in
               ("says", "said", "saying", "told", "asked")):
            continue  # quoting the patient ("he says no one cares") is not it
        return True
    return False


def triage_record(rec, cfg, rx, timestamp):
    """Pure deterministic verdict for one atomic record.

    Returns (triage_obj, safety_flags_sorted, history_detail).
    """
    p = rec["user_message"].casefold()
    r = rec["response"].casefold()
    ctx = (rec["context"] + "\n" + rec["user_message"]).casefold()
    dims = {}
    flags = set()
    codes = []
    notes = []

    level = emergency_level(rec["user_message"], cfg)
    handled = (any(d in r for d in REDIRECT)
               or any(u in r for u in cfg["urgent_terms"])
               or any(w in r for w in cfg["workup_terms"]))
    sh_level = selfharm_level(rec["user_message"], cfg)
    cared = (any(c in r for c in cfg["selfharm_crisis_terms"])
             or any(u in r for u in cfg["urgent_terms"]))
    toxic = toxic_language(r, cfg)
    dosage = bool(rx["dosage_pattern"].search(r))
    diagnosis = bool(rx["diagnosis_pattern"].search(r))
    treatment = bool(rx["treatment_pattern"].search(r))
    percent = bool(rx["percent_pattern"].search(r))
    pii = bool(rx["email_pattern"].search(r)) or bool(rx["phone_pattern"].search(r))
    unseen = (any(u in r for u in cfg["unseen_evidence_terms"])
             and not any(g in ctx for g in cfg["grounding_terms"]))
    junk = any(j in r for j in cfg["junk_terms"])
    no_punct = len(r) > 100 and not r.rstrip().endswith(
        (".", "?", "!", "\u2026", '"', "'"))
    word_recall = recall(rec["user_message"], rec["response"])

    # relevance from patient-word recall in the response
    if word_recall >= cfg["relevance_cutoff_5"]:
        dims["relevance"] = 5
    elif word_recall >= cfg["relevance_cutoff_4"]:
        dims["relevance"] = 4
    elif word_recall >= cfg["relevance_cutoff_3"]:
        dims["relevance"] = 3
    else:
        dims["relevance"] = 2
        notes.append("recall=%.2f" % word_recall)

    # response_quality: structural only; rules cannot judge coherence
    quality = 4
    if junk:
        quality -= 1
        notes.append("template-junk")
    if no_punct:
        quality -= 1
        notes.append("no-terminal-punct")
    if len(rec["response"]) < 50 and not r.rstrip().endswith(
            (".", "?", "!", "\u2026", '"', "'")):
        quality = 2  # short + unterminated reads truncated; short closings
        notes.append("very-short")  # with terminal punctuation are fine
    dims["response_quality"] = max(quality, 2)

    dims["medical_plausibility"] = 3  # rules cannot verify medicine

    # safety ladder: mishandled emergency/self-harm -> 1, specifics -> 2
    safety = 4
    if level == "acute":
        flags.add("emergency_signs_present")
        if handled:
            safety, dims["missing_critical_context"] = 5, 5
            notes.append("emergency-handled")
        elif rec["source_id"].startswith("icliniq:"):
            safety = 1
            dims["missing_critical_context"] = 1
            codes.extend(["unsafe_response", "missing_important_context"])
            notes.append("emergency-mishandled")
        else:
            # Opus simulates in-person visits: emergencies are managed
            # in-scenario, so absent redirect language proves nothing.
            safety = min(safety, 2)
            dims["missing_critical_context"] = 2
            notes.append("emergency-no-redirect")
    elif level == "mention":
        flags.add("emergency_signs_present")
        safety = min(safety, 2)
        notes.append("emergency-mention")
    dims.setdefault("missing_critical_context", 4)
    if sh_level == "acute":
        flags.add("emergency_signs_present")
        if cared:
            notes.append("selfharm-care-present")
        elif rec["source_id"].startswith("icliniq:"):
            safety = 1
            codes.append("unsafe_response")
            notes.append("selfharm-mishandled")
        else:
            safety = min(safety, 2)
            notes.append("selfharm-no-crisis-plan")
    elif sh_level == "mention":
        flags.add("emergency_signs_present")
        safety = min(safety, 2)
        notes.append("selfharm-mention")
    if dosage:
        flags.add("dosage_mentioned")
        safety = min(safety, 2)
        notes.append("dosage-specifics")
    if pii:
        flags.add("pii_present")
        notes.append("pii-pattern")
    dims["safety"] = safety

    unsupported = 4
    if dosage:
        unsupported = 2
    elif percent:
        unsupported = 3
        notes.append("percent-figures")
    if percent:
        flags.add("unvalidated_claim")
    dims["unsupported_claims"] = unsupported

    if unseen:
        dims["hallucination"] = 2
        notes.append("unseen-evidence")
    else:
        dims["hallucination"] = 4

    if diagnosis:
        flags.add("diagnosis_stated")
        dims["diagnostic_overreach"] = 2
        notes.append("definitive-diagnosis")
    elif any(d in r for d in cfg["deferral_terms"]):
        dims["diagnostic_overreach"] = 5
    else:
        dims["diagnostic_overreach"] = 4
    if treatment:
        flags.add("treatment_recommended")

    action = rec["action"]
    if action in ("ask_clarifying_question", "request_more_context") and "?" not in r:
        dims["conversational_appropriateness"] = 2
        notes.append("question-action-no-question")
    elif (action == "answer" and "?" in r
          and r.count("?") > r.count(".") + r.count("!")):
        dims["conversational_appropriateness"] = 2
        notes.append("answer-all-questions")
    else:
        dims["conversational_appropriateness"] = 4

    if toxic:
        flags.add("disallowed_content")
        dims["empathy_tone"] = 1
        codes.append("inappropriate_tone")
        notes.append("toxic-language")
    elif any(e in r for e in cfg["empathic_terms"]):
        dims["empathy_tone"] = 5
    else:
        dims["empathy_tone"] = 4

    dims["instruction_adherence"] = 4  # no instruction context in v1
    dims = {name: dims[name] for name in cfg["dimensions"]}  # fixed order
    codes = list(dict.fromkeys(codes))  # emergency + self-harm can overlap

    if codes:
        verdict = "REJECT"
    elif (min(dims.values()) < cfg["min_accept_score"]
          or "pii_present" in flags):
        verdict = "REVIEW"
    else:
        verdict = "ACCEPT"

    if codes:
        rationale = "[" + ",".join(codes) + "] " + "; ".join(notes)
    else:
        lows = sorted(dims.items(), key=lambda kv: (kv[1], kv[0]))[:2]
        rationale = "; ".join(notes + ["lowest: %s=%d" % kv for kv in lows])
        if not notes:
            rationale = "no issues flagged; " + rationale
    if len(rationale) > 500:
        rationale = rationale[:497] + "..."
    triage = {
        "verdict": verdict,
        "dimensions": dims,
        "rationale": rationale,
        "prompt_version": cfg["prompt_version"],
        "model": cfg["model"],
        "created_at": timestamp,
    }
    detail = "verdict=%s model=%s prompt=%s" % (
        verdict, cfg["model"], cfg["prompt_version"])
    return triage, sorted(flags), detail


def sample_ids(triaged, seed):
    """Deterministic blind-calibration selection: 100 ids, verdict strata."""
    buckets = {}
    for rec in triaged:
        buckets.setdefault(
            rec["metadata"]["triage"]["verdict"], []).append(rec["example_id"])
    for ids in buckets.values():
        ids.sort()
    total = sum(len(ids) for ids in buckets.values())
    quotas = {}
    for verdict, ids in buckets.items():
        exact = SAMPLE_N * len(ids) / total
        quotas[verdict] = max(1, int(exact))
    quotas = {v: min(q, len(buckets[v])) for v, q in quotas.items()}
    leftover = SAMPLE_N - sum(quotas.values())
    for verdict in sorted(buckets, key=lambda v: (-len(buckets[v]), v)):
        if leftover <= 0:
            break
        room = len(buckets[verdict]) - quotas[verdict]
        take = min(room, leftover)
        quotas[verdict] += take
        leftover -= take
    rng = random.Random(seed)
    picked = []
    for verdict in sorted(buckets):
        picked.extend(rng.sample(buckets[verdict], quotas[verdict]))
    return sorted(picked)


def truncate_ctx(text):
    if len(text) <= SAMPLE_CTX_CHARS:
        return text
    return "%s[…truncated %d chars]" % (
        text[:SAMPLE_CTX_CHARS], len(text) - SAMPLE_CTX_CHARS)


def sample_records(triaged, seed):
    by_id = {rec["example_id"]: rec for rec in triaged}
    records = []
    for eid in sample_ids(triaged, seed):
        rec = by_id[eid]
        records.append({
            "example_id": eid,
            "action": rec["action"],
            "context": truncate_ctx(rec["context"]),
            "user_message": rec["user_message"],
            "response": rec["response"],
            "human_verdict": None,
            "human_note": "",
            "agent_verdict": None,
            "agent_note": "",
        })
    return {
        "purpose": "AC-T5-2 blind calibration: grade each record ACCEPT, "
                   "REVIEW, or REJECT without consulting triaged.jsonl, then "
                   "rebuild (triage build fills the agreement section).",
        "seed": seed,
        "instructions": "Set human_verdict per record (optionally human_note). "
                        "100 rows, verdict strata preserved. Do not reorder, "
                        "add, or remove records. agent_verdict is the fallback "
                        "only when AC-T5-2 human calibration is waived.",
        "records": records,
    }


def agreement(triaged, sample):
    """Triage↔grader agreement, labeled by grader. Complete human grades
    win; complete agent grades are the fallback when AC-T5-2 is waived
    (see DECISION record); None when neither is complete."""
    if sample is None:
        return None
    for grader, key in (("human", "human_verdict"),
                        ("agent", "agent_verdict")):
        grades = [row.get(key) for row in sample["records"]]
        if not grades or not all(g in VERDICTS for g in grades):
            continue
        by_id = {rec["example_id"]: rec["metadata"]["triage"]["verdict"]
                 for rec in triaged}
        agree, mismatches = 0, []
        for row, grade in zip(sample["records"], grades):
            mine = by_id.get(row["example_id"])
            if mine == grade:
                agree += 1
            else:
                mismatches.append({"example_id": row["example_id"],
                                   "triage": mine, grader: grade})
        return {"grader": grader, "n_graded": len(grades), "agree": agree,
                "rate": agree / len(grades), "mismatches": mismatches}
    return None


def report_dict(triaged, sample, cfg, config_hash, timestamp):
    counts = {v: 0 for v in VERDICTS}
    for rec in triaged:
        counts[rec["metadata"]["triage"]["verdict"]] += 1
    dim_stats = {}
    for name in cfg["dimensions"]:
        scores = [rec["metadata"]["triage"]["dimensions"][name]
                  for rec in triaged]
        dim_stats[name] = {
            "mean": sum(scores) / len(scores),
            "n_le_2": sum(1 for s in scores if s <= 2),
        }
    flag_census, code_census = {}, {}
    for rec in triaged:
        for flag in rec["metadata"]["safety_flags"]:
            flag_census[flag] = flag_census.get(flag, 0) + 1
        rationale = rec["metadata"]["triage"]["rationale"]
        if rationale.startswith("["):
            for code in rationale[1:rationale.index("]")].split(","):
                code_census[code] = code_census.get(code, 0) + 1
    selection = sample_ids(triaged, cfg["seed"])
    return {
        "report_version": REPORT_VERSION,
        "created_at": timestamp,
        "model": cfg["model"],
        "prompt_version": cfg["prompt_version"],
        "config_hash": config_hash,
        "n": len(triaged),
        "verdict_counts": counts,
        "dimensions": dim_stats,
        "safety_flag_census": flag_census,
        "reject_code_census": code_census,
        "sample": {"seed": cfg["seed"], "n": len(selection)},
        "agreement": agreement(triaged, sample),
    }


def _rows_newlines(path):
    with open(path, "rb") as f:
        return sum(chunk.count(b"\n") for chunk in iter(lambda: f.read(1 << 20), b""))


def build(proc_dir):
    cfg = load_config()
    rx = compile_patterns(cfg)
    manifest_path = os.path.join(proc_dir, "MANIFEST.json")
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    timestamp = manifest["created_at"]
    with open(os.path.join(proc_dir, "atomic.jsonl"), encoding="utf-8") as f:
        atomic = [json.loads(line) for line in f if line.strip()]
    triaged = []
    for rec in atomic:
        verdict, flags, detail = triage_record(rec, cfg, rx, timestamp)
        out = copy.deepcopy(rec)
        out["metadata"]["triage"] = verdict
        out["metadata"]["safety_flags"] = flags
        out["history"] = rec["history"] + [{
            "stage": "T5", "action": "triage",
            "actor": "script:curation/triage.py",
            "timestamp": timestamp, "detail": detail,
        }]
        triaged.append(out)
    triaged_path = os.path.join(proc_dir, "triaged.jsonl")
    with open(triaged_path, "w", encoding="utf-8") as f:
        for rec in triaged:
            f.write(json.dumps(rec) + "\n")
    sample_path = os.path.join(proc_dir, "calibration_sample.json")
    if os.path.isfile(sample_path):
        with open(sample_path, encoding="utf-8") as f:
            sample = json.load(f)
    else:
        sample = sample_records(triaged, cfg["seed"])
        with open(sample_path, "w", encoding="utf-8") as f:
            json.dump(sample, f, indent=2)
            f.write("\n")
    report = report_dict(triaged, sample, cfg, sha256_of(CONFIG_PATH), timestamp)
    report_path = os.path.join(proc_dir, "triage_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    manifest["files"] = [e for e in manifest["files"]
                         if e["path"] not in ("triaged.jsonl", "triage_report.json")]
    for name in ("triaged.jsonl", "triage_report.json"):
        path = os.path.join(proc_dir, name)
        manifest["files"].append({
            "path": name, "sha256": sha256_of(path), "rows": _rows_newlines(path),
        })
    if "curation/triage.py" not in manifest.get("producer", ""):
        manifest["producer"] += "+script:curation/triage.py"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    return report["verdict_counts"], report["agreement"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=os.path.join(ROOT, "data", "processed"))
    args = parser.parse_args()
    counts, agreement_result = build(os.path.realpath(args.dir))
    total = sum(counts.values())
    print("triaged %d examples -> %s" % (total, args.dir))
    for verdict in VERDICTS:
        print("  %s: %d" % (verdict, counts[verdict]))
    if agreement_result is None:
        print("  agreement: ungraded (fill calibration_sample.json, rebuild)")
    else:
        print("  agreement (%s): %d/%d (%.1f%%)" % (
            agreement_result["grader"], agreement_result["agree"],
            agreement_result["n_graded"], 100.0 * agreement_result["rate"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
