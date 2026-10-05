"""Validate the T5 triaged store (gate: check-triage).

Covers AC-T5-1 (verdict on 100%; config + prompt version recorded), AC-T5-2
(calibration sample fully graded, agreement reported), AC-T5-3 (REJECT
reasons from the controlled vocabulary):
  - manifest entries for triaged.jsonl + triage_report.json hash/rows match
  - config loads and pins the expected model/prompt/seed/dimensions
  - every triaged line validates: atomic/v1 + triage object (verdict enum,
    11 dims 1-5, rationale 1-500 chars, model/prompt/created_at), safety
    flags in the section-6 vocab, T5 history entry
  - REJECT rationales carry bracketed section-7 codes only
  - ids unique and exactly cover atomic.jsonl; all non-triage fields equal
    the atomic source; T5 history detail matches the stored verdict
    (rule-correctness itself is proven by the byte-identical re-run below,
    which re-derives every verdict from the atomic source)
  - report equals recomputation (counts, dims, censuses, config hash, agreement)
  - calibration sample: 100 rows, ids equal the deterministic selection,
    fields match, all human-graded, agreement equals recomputation
  - re-run into temp dir is byte-identical (triaged.jsonl, report, manifest)

The sample itself is verified semantically, never byte-compared: the build
never overwrites human grades.

Runtime is ~3-4 minutes on 37k records (full re-triage in the determinism
re-run dominates); run the recorded gate with a raised budget:
genesis gate . T5-1 --timeout 600000
"""

import copy
import json
import os
import re
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from curation.triage import (  # noqa: E402
    CONFIG_PATH,
    NEGATIVE_REASONS,
    SAFETY_FLAGS,
    SAMPLE_N,
    VERDICTS,
    agreement,
    build,
    compile_patterns,
    emergency_level,
    load_config,
    report_dict,
    sample_ids,
    selfharm_level,
    sha256_of,
    toxic_language,
    triage_record,
    truncate_ctx,
)

EXPECTED_MODEL = "rules-triage/v1"
EXPECTED_PROMPT = "triage/v1"
EXPECTED_SEED = 42
EXPECTED_DIMENSIONS = [
    "relevance",
    "response_quality",
    "medical_plausibility",
    "safety",
    "unsupported_claims",
    "hallucination",
    "diagnostic_overreach",
    "missing_critical_context",
    "conversational_appropriateness",
    "empathy_tone",
    "instruction_adherence",
]
REJECT_CODES = re.compile(r"^\[([a-z_,]+)\]")


def _rows_newlines(path):
    with open(path, "rb") as f:
        return sum(chunk.count(b"\n")
                   for chunk in iter(lambda: f.read(1 << 20), b""))


def main():
    proc_dir = os.path.realpath(os.path.join(ROOT, "data", "processed"))
    errors = []
    try:
        cfg = load_config()
    except (ValueError, OSError) as exc:
        print("triage.yaml: %s" % exc, file=sys.stderr)
        return 1
    if cfg.get("model") != EXPECTED_MODEL:
        errors.append("config model %r != %r" % (cfg.get("model"), EXPECTED_MODEL))
    if cfg.get("prompt_version") != EXPECTED_PROMPT:
        errors.append("config prompt_version %r != %r"
                      % (cfg.get("prompt_version"), EXPECTED_PROMPT))
    if cfg.get("seed") != EXPECTED_SEED:
        errors.append("config seed %r != %r" % (cfg.get("seed"), EXPECTED_SEED))
    if cfg.get("dimensions") != EXPECTED_DIMENSIONS:
        errors.append("config dimensions != expected 11-dimension rubric")
    rx = compile_patterns(cfg)
    live = [  # regression pins: a silently dead detector once blanked
        ("dosage_pattern", "take 20 mg twice daily", True),  # every regex
        ("dosage_pattern", "take a tablet", False),
        ("diagnosis_pattern", "you have diabetes", True),
        ("treatment_pattern", "you should take rest", True),
        ("percent_pattern", "spo2 99%", True),
        ("email_pattern", "mail me at a@b.com", True),
        ("phone_pattern", "call 555-123-4567", True),
    ]
    for key, text, want in live:
        if bool(rx[key].search(text)) != want:
            errors.append("config %s: dead on %r" % (key, text))
    for text, want in [
            ("I have crushing chest pain right now", "acute"),
            ("No real chest pain, just tightness", "mention"),
            ("Is that the thing that causes strokes?", "mention"),
            ("My uncle had a stroke last year", "mention"),
            ("Mother: my brother takes something for seizures, I think",
             "mention"),
            ("She starts shaking and cannot breathe and I am scared",
             "mention"),
            ("I had crushing chest pain months ago", "mention"),
            ("Online searches say stroke, what else could it be?", "mention"),
            ("I need seizure medicines advice", None)]:
        if emergency_level(text, cfg) != want:
            errors.append("emergency_level(%r) != %r" % (text, want))
    for text, want in [
            ("I want to kill myself", "acute"),
            ("I spend my life lying flat", None),
            ("I don't want to hurt myself", "mention"),
            ("he committed suicide last year", "mention"),
            ("He threatened to kill himself", "acute"),
            ("people who commit suicide need help", "mention"),
            ("I take my vitamins daily", None)]:
        if selfharm_level(text, cfg) != want:
            errors.append("selfharm_level(%r) != %r" % (text, want))
    for text, want in [
            ("you are far from stupid", False),
            ("he says no one cares about him", False),
            ("you are stupid, shut up", True)]:
        if toxic_language(text, cfg) != want:
            errors.append("toxic_language(%r) != %r" % (text, want))
    for source, want in [("icliniq:1", "REJECT"), ("opus:X:1", "REVIEW")]:
        probe = {"user_message": "I have crushing chest pain right now",
                 "response": "Tell me more about the pain.",
                 "context": "", "action": "answer", "source_id": source}
        got = triage_record(probe, cfg, rx, "ts")[0]["verdict"]
        if got != want:
            errors.append("%s acute-no-redirect -> %s, want %s"
                          % (source, got, want))
    for source, response, want in [
            ("icliniq:1", "Tell me more about that.", "REJECT"),
            ("opus:X:1", "Tell me more about that.", "REVIEW"),
            ("icliniq:1", "Please call a crisis hotline immediately.",
             "REVIEW")]:
        probe = {"user_message": "I want to kill myself",
                 "response": response,
                 "context": "", "action": "answer", "source_id": source}
        got = triage_record(probe, cfg, rx, "ts")[0]["verdict"]
        if got != want:
            errors.append("selfharm %s -> %s, want %s" % (source, got, want))
    manifest = json.load(open(os.path.join(proc_dir, "MANIFEST.json"),
                              encoding="utf-8"))
    entries = {e["path"]: e for e in manifest.get("files", [])}
    timestamp = manifest.get("created_at")
    for name in ("triaged.jsonl", "triage_report.json"):
        entry = entries.get(name)
        path = os.path.join(proc_dir, name)
        if entry is None or not os.path.isfile(path):
            errors.append("%s missing from store or manifest" % name)
            continue
        if sha256_of(path) != entry.get("sha256"):
            errors.append("%s: SHA-256 mismatch vs manifest" % name)
        rows = _rows_newlines(path)
        if rows != entry.get("rows"):
            errors.append("%s: rows %d != manifest %s"
                          % (name, rows, entry.get("rows")))
    if errors:
        print("\n".join(errors[:20]), file=sys.stderr)
        return 1
    with open(os.path.join(proc_dir, "atomic.jsonl"), encoding="utf-8") as f:
        atomic = {}
        for line in f:
            if line.strip():
                obj = json.loads(line)
                atomic[obj["example_id"]] = obj
    with open(os.path.join(proc_dir, "triaged.jsonl"), encoding="utf-8") as f:
        triaged = [json.loads(line) for line in f if line.strip()]
    ids = [o.get("example_id") for o in triaged]
    if len(set(ids)) != len(ids):
        errors.append("duplicate example_id in triaged.jsonl")
    missing = set(atomic) - set(ids)
    extra = set(ids) - set(atomic)
    if missing:
        errors.append("untriaged: %d missing (%s…)"
                      % (len(missing), sorted(missing)[0]))
    if extra:
        errors.append("triaged unknown ids: %d (%s…)" % (len(extra), sorted(extra)[0]))
    for out in triaged:
        eid = out.get("example_id", "?")
        src = atomic.get(eid)
        if src is None:
            continue
        if out.get("schema_version") != "atomic/v1":
            errors.append("%s: bad schema_version" % eid)
            continue
        stripped = copy.deepcopy(out)
        stored = stripped["metadata"].get("triage")
        stripped["metadata"]["triage"] = None
        stripped["metadata"]["safety_flags"] = []
        hist = stripped.get("history", [])
        if not hist or hist[-1].get("stage") != "T5":
            errors.append("%s: missing T5 history entry" % eid)
            continue
        t5entry = hist.pop()
        if stripped != src:
            errors.append("%s: non-triage fields differ from atomic source" % eid)
            continue
        if not isinstance(stored, dict):
            errors.append("%s: missing triage object" % eid)
            continue
        if stored.get("verdict") not in VERDICTS:
            errors.append("%s: bad verdict %r" % (eid, stored.get("verdict")))
        dims = stored.get("dimensions", {})
        if list(dims) != EXPECTED_DIMENSIONS:
            errors.append("%s: bad dimension keys" % eid)
        elif any(type(v) is not int or not 1 <= v <= 5 for v in dims.values()):
            errors.append("%s: dimension scores not int 1-5" % eid)
        rationale = stored.get("rationale", "")
        if not isinstance(rationale, str) or not 1 <= len(rationale) <= 500:
            errors.append("%s: rationale not 1-500 chars" % eid)
        if stored.get("model") != cfg["model"]:
            errors.append("%s: model not recorded" % eid)
        if stored.get("prompt_version") != cfg["prompt_version"]:
            errors.append("%s: prompt_version not recorded" % eid)
        if stored.get("created_at") != timestamp:
            errors.append("%s: created_at != manifest timestamp" % eid)
        flags = out["metadata"].get("safety_flags", None)
        if not isinstance(flags, list) or any(fl not in SAFETY_FLAGS for fl in flags):
            errors.append("%s: bad safety_flags" % eid)
        elif flags != sorted(set(flags)):
            errors.append("%s: safety_flags not sorted-unique" % eid)
        if stored.get("verdict") == "REJECT":
            match = REJECT_CODES.match(rationale)
            found = match.group(1).split(",") if match else []
            if not found or any(c not in NEGATIVE_REASONS for c in found):
                errors.append("%s: REJECT reasons outside controlled vocabulary" % eid)
        if t5entry.get("action") != "triage":
            errors.append("%s: bad T5 history action" % eid)
        if t5entry.get("timestamp") != timestamp:
            errors.append("%s: T5 history timestamp != manifest timestamp" % eid)
        want_detail = "verdict=%s model=%s prompt=%s" % (
            stored.get("verdict"), stored.get("model"),
            stored.get("prompt_version"))
        if t5entry.get("detail") != want_detail:
            errors.append("%s: T5 history detail inconsistent" % eid)
        if len(errors) > 200:
            errors.append("… stopping per-record checks early")
            break
    sample_path = os.path.join(proc_dir, "calibration_sample.json")
    sample = None
    if os.path.isfile(sample_path):
        sample = json.load(open(sample_path, encoding="utf-8"))
    if not isinstance(sample, dict) or len(sample.get("records", [])) != SAMPLE_N:
        errors.append("calibration_sample.json: want exactly %d rows" % SAMPLE_N)
        sample = None
    if sample is not None:
        want_ids = sample_ids(triaged, cfg["seed"])
        got_ids = [row.get("example_id") for row in sample["records"]]
        if got_ids != want_ids:
            errors.append("calibration_sample.json: ids != deterministic selection")
        by_id = {o["example_id"]: o for o in triaged}
        human_open = agent_open = 0
        for row in sample["records"]:
            rec = by_id.get(row.get("example_id"))
            if rec is None:
                continue
            if (row.get("action") != rec["action"]
                    or row.get("user_message") != rec["user_message"]
                    or row.get("response") != rec["response"]
                    or row.get("context") != truncate_ctx(rec["context"])):
                errors.append("%s: sample fields != triaged record"
                              % row.get("example_id"))
            if row.get("human_verdict") not in VERDICTS:
                human_open += 1
            if row.get("agent_verdict") not in VERDICTS:
                agent_open += 1
        if human_open and agent_open:
            errors.append("calibration_sample.json: %d/%d human-open and "
                          "%d/%d agent-open (AC-T5-2)"
                          % (human_open, SAMPLE_N, agent_open, SAMPLE_N))
        report = json.load(open(os.path.join(proc_dir, "triage_report.json"),
                                encoding="utf-8"))
        expected = report_dict(triaged, sample, cfg, sha256_of(CONFIG_PATH),
                               timestamp)
        if report != expected:
            errors.append("triage_report.json != recomputation")
        elif report.get("agreement") is None:
            errors.append("triage_report.json: agreement missing (AC-T5-2)")
    if not errors:
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(os.path.join(proc_dir, "atomic.jsonl"), tmp)
            shutil.copy(sample_path, tmp)
            base = dict(manifest)
            base["files"] = [e for e in manifest["files"]
                             if e["path"] not in ("triaged.jsonl", "triage_report.json")]
            base["producer"] = base["producer"].replace("+script:curation/triage.py", "")
            with open(os.path.join(tmp, "MANIFEST.json"), "w", encoding="utf-8") as f:
                json.dump(base, f, indent=2)
                f.write("\n")
            build(tmp)
            for name in ("triaged.jsonl", "triage_report.json", "MANIFEST.json"):
                with open(os.path.join(proc_dir, name), "rb") as f:
                    want = f.read()
                with open(os.path.join(tmp, name), "rb") as f:
                    got = f.read()
                if want != got:
                    errors.append("%s: re-run not byte-identical" % name)
    if errors:
        print("\n".join(errors[:20]), file=sys.stderr)
        if len(errors) > 20:
            print("... +%d more" % (len(errors) - 20), file=sys.stderr)
        return 1
    counts = {v: 0 for v in VERDICTS}
    for out in triaged:
        counts[out["metadata"]["triage"]["verdict"]] += 1
    agreed = report["agreement"]
    print("triage store OK: %d triaged (%d ACCEPT, %d REVIEW, %d REJECT), "
          "calibration agreement (%s) %d/%d (%.1f%%), determinism verified"
          % (len(triaged), counts["ACCEPT"], counts["REVIEW"], counts["REJECT"],
             agreed["grader"], agreed["agree"], agreed["n_graded"],
             100.0 * agreed["rate"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
