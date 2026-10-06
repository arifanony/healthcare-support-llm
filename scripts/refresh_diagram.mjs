// Refresh the Archify pipeline diagram from live Genesis state.
//
// Reads .genesis/project.json (task states) + data manifests (row counts),
// patches ONLY status/count/freshness fields in candidate.json (never
// geometry: pos/size/via/labelDx/labelDy are hand-placed), then re-runs
// `archify finalize`. Re-run after any gate pass or checkpoint:
//
//   node scripts/refresh_diagram.mjs
//
// Options (paths resolve against the repo root):
//   --candidate <p>  candidate JSON (default .archify/.../candidate.json)
//   --output <p>     output HTML (default alongside the candidate)
//   --project <p>    project.json (default .genesis/project.json)
//
// When T7+ stores land with their own manifests, extend STORE_MANIFESTS.
import fs from 'fs';
import path from 'path';
import os from 'os';
import { fileURLToPath } from 'url';
import { execFileSync } from 'child_process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, '..');
const FOLDER = '.archify/architecture-pipeline-20261006-174721';
const DEFAULT_CANDIDATE = `${FOLDER}/candidate.json`;
const DEFAULT_OUTPUT = `${FOLDER}/pipeline.html`;
const DEFAULT_PROJECT = '.genesis/project.json';

const COMPONENT_TASK = {
  spec: 'SPEC-1', t2: 'T2-1', t3: 'T3-1', t4: 'T4-1', t5: 'T5-1', t6: 'T6-1',
  t7: 'T7-1', t8: 'T8-1', t9: 'T9-1', t10: 'T10-1', t11: 'T11-1', t12: 'T12-1', t13: 'T13-1',
};
const STATE_STYLE = {
  done: { tag: 'done', icon: 'success' },
  active: { tag: 'active', icon: 'active' },
  queued: { tag: 'queued', icon: 'waiting' },
  failed: { tag: 'failed', icon: 'failure' },
};
// Flow id -> target component id (drives emphasis vs dashed). f-nogo-rework
// is intentionally absent: it always stays the security variant.
const FLOW_TARGET = {
  'f-opus-ingest': 't2', 'f-icliniq-ingest': 't2', 'f-spec-ingest': 't2',
  'f-ingest-rawstore': 'store-raw', 'f-rawstore-structure': 't3',
  'f-structure-conv': 'store-conv', 'f-conv-extract': 't4',
  'f-extract-atomic': 'store-atomic', 'f-atomic-triage': 't5',
  'f-triage-graded': 'store-triaged', 'f-graded-review': 't6',
  'f-review-curated': 't7', 'f-curated-store': 'store-curated',
  'f-store-quality': 't8', 'f-quality-splits': 't9',
  'f-splits-store': 'store-splits', 'f-store-train': 't10',
  'f-train-runs': 'store-runs', 'f-runs-compare': 't11',
  'f-compare-analyze': 't12', 'f-analyze-repro': 't13',
};
const STORE_MANIFESTS = {
  'store-raw': 'data/raw/MANIFEST.json',
  'store-conv': 'data/processed/MANIFEST.json',
  'store-atomic': 'data/processed/MANIFEST.json',
  'store-triaged': 'data/processed/MANIFEST.json',
  'store-curated': 'data/curated/MANIFEST.json',
  'store-splits': 'data/splits/MANIFEST.json',
  'store-runs': 'experiments/MANIFEST.json',
};

const fmt = (n) => Number(n).toLocaleString('en-US');
const readJson = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
const tryReadJson = (p) => { try { return readJson(p); } catch { return null; } };
function args() {
  const out = {};
  const argv = process.argv.slice(2);
  for (let i = 0; i < argv.length; i += 2) {
    const k = argv[i];
    if (k === '--candidate') out.candidate = argv[i + 1];
    else if (k === '--output') out.output = argv[i + 1];
    else if (k === '--project') out.project = argv[i + 1];
  }
  return out;
}
const manifestRows = (m, match) => {
  if (!m || !Array.isArray(m.files)) return null;
  const f = m.files.find((x) => match.test(x.path));
  return f && Number.isInteger(f.rows) ? f.rows : null;
};

function main() {
  const o = args();
  const candRel = (o.candidate || DEFAULT_CANDIDATE).replace(/\\/g, '/');
  const outRel = (o.output || DEFAULT_OUTPUT).replace(/\\/g, '/');
  const projPath = path.resolve(ROOT, o.project || DEFAULT_PROJECT);
  const candPath = path.resolve(ROOT, candRel);

  const project = readJson(projPath);
  const states = {};
  for (const t of project.tasks || []) states[t.id] = t.state;

  const rawM = tryReadJson(path.join(ROOT, 'data/raw/MANIFEST.json'));
  const procM = tryReadJson(path.join(ROOT, 'data/processed/MANIFEST.json'));
  const report = tryReadJson(path.join(ROOT, 'data/processed/triage_report.json'));
  const counts = {
    opus: manifestRows(rawM, /opus/i),
    icliniq: manifestRows(rawM, /icliniq/i),
    raw: (manifestRows(rawM, /opus/i) || 0) + (manifestRows(rawM, /icliniq/i) || 0) || null,
    conv: manifestRows(procM, /^conversations\.jsonl$/),
    quar: manifestRows(procM, /^quarantine\.jsonl$/),
    atomic: manifestRows(procM, /^atomic\.jsonl$/),
    triaged: manifestRows(procM, /^triaged\.jsonl$/),
    acc: report && report.verdict_counts ? report.verdict_counts.ACCEPT : null,
    rev: report && report.verdict_counts ? report.verdict_counts.REVIEW : null,
    rej: report && report.verdict_counts ? report.verdict_counts.REJECT : null,
  };
  if (rawM && counts.raw === null) {
    const sum = rawM.files.reduce((a, f) => a + (f.rows || 0), 0);
    counts.raw = sum || null;
  }

  const cand = readJson(candPath);
  const byId = {};
  for (const c of cand.components) byId[c.id] = c;

  // Task nodes: tag + icon mirror Genesis state.
  const applied = {};
  for (const [compId, taskId] of Object.entries(COMPONENT_TASK)) {
    const st = states[taskId];
    const style = STATE_STYLE[st] || { tag: st || 'unknown', icon: 'neutral' };
    if (byId[compId]) { byId[compId].tag = style.tag; byId[compId].icon = style.icon; }
    applied[taskId] = st || null;
  }
  // Raw input nodes: live counts.
  if (counts.opus !== null && byId['raw-opus']) byId['raw-opus'].sublabel = `${fmt(counts.opus)} chats · MIT`;
  if (counts.icliniq !== null && byId['raw-icliniq']) byId['raw-icliniq'].sublabel = `${fmt(counts.icliniq)} · academic-only`;
  // Store nodes: backing manifest present -> counts; absent -> planned.
  const storeLive = {};
  const storeCount = {
    'store-raw': counts.raw, 'store-conv': counts.conv,
    'store-atomic': counts.atomic, 'store-triaged': counts.triaged,
  };
  for (const [storeId, manifest] of Object.entries(STORE_MANIFESTS)) {
    const node = byId[storeId];
    if (!node) continue;
    const backing = path.join(ROOT, manifest);
    if (fs.existsSync(backing) && (storeCount[storeId] || manifestRows(tryReadJson(backing), /./))) {
      const n = storeCount[storeId] !== undefined && storeCount[storeId] !== null
        ? storeCount[storeId]
        : (tryReadJson(backing).files || []).reduce((a, f) => a + (f.rows || 0), 0);
      node.tag = `${fmt(n)} rows`;
      node.icon = 'neutral';
      if (storeId === 'store-raw') node.sublabel = `${fmt(n)} · hash-verified`;
      else if (storeId === 'store-conv') node.sublabel = `${fmt(n)} · ${counts.quar || 0} quarantined`;
      else if (storeId === 'store-atomic') node.sublabel = `${fmt(n)} parent-linked`;
      else if (storeId === 'store-triaged') node.sublabel = `${fmt(n)} graded`;
      else node.sublabel = `${fmt(n)} rows`;
      storeLive[storeId] = true;
    } else {
      node.tag = 'planned';
      node.icon = 'waiting';
      storeLive[storeId] = false;
    }
  }
  // Flows: live target -> emphasis, else dashed. Count labels refresh too.
  const labelFor = {
    'f-opus-ingest': counts.opus !== null ? `${fmt(counts.opus)} chats` : null,
    'f-icliniq-ingest': counts.icliniq !== null ? `${fmt(counts.icliniq)} rows` : null,
    'f-ingest-rawstore': counts.raw !== null ? `${fmt(counts.raw)} verified` : null,
    'f-structure-conv': counts.conv !== null ? `${fmt(counts.conv)} normalized` : null,
    'f-extract-atomic': counts.atomic !== null ? `${fmt(counts.atomic)} examples` : null,
    'f-triage-graded': counts.acc !== null ? `${fmt(counts.acc)} / ${fmt(counts.rev)} / ${fmt(counts.rej)}` : null,
    'f-graded-review': counts.rev !== null ? `${fmt(counts.rev)} to review` : null,
  };
  for (const f of cand.connections || []) {
    if (labelFor[f.id] !== undefined && labelFor[f.id] !== null) f.label = labelFor[f.id];
    const target = FLOW_TARGET[f.id];
    if (!target) continue;
    const taskId = COMPONENT_TASK[target];
    const live = taskId
      ? (states[taskId] === 'done' || states[taskId] === 'active')
      : !!storeLive[target];
    f.variant = live ? 'emphasis' : 'dashed';
  }
  // Freshness: HEAD revision + date.
  let head = null;
  try {
    head = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: ROOT, encoding: 'utf8' }).trim();
    if (!/^[0-9a-f]{40}$/.test(head)) head = null;
  } catch { head = null; }
  if (head && cand.meta && cand.meta.repository) cand.meta.repository.revision = head;
  const today = `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}-${String(new Date().getDate()).padStart(2, '0')}`;
  for (const card of cand.cards || []) {
    if (card.title === 'Freshness' && card.items && card.items[0]) {
      card.items[0] = `Snapshot of .genesis/project.json at ${head ? head.slice(0, 7) : 'unknown'} (${today}).`;
    }
  }
  cand.meta.output = outRel;
  fs.mkdirSync(path.dirname(candPath), { recursive: true });
  fs.writeFileSync(candPath, JSON.stringify(cand, null, 2) + '\n');

  const archify = process.env.ARCHIFY_BIN || path.join(os.homedir(), '.agents/skills/archify/bin/archify.mjs');
  if (!fs.existsSync(archify)) throw new Error(`archify not found at ${archify} (set ARCHIFY_BIN)`);
  // The browser gate refuses to overwrite a receipt owned by older artifact
  // bytes; it is regenerable, so move it aside before every finalize.
  try { fs.unlinkSync(path.resolve(ROOT, outRel).replace(/\.html$/, '.browser-check.json')); } catch {}
  let res;
  try {
    res = execFileSync('node', [archify, 'finalize', 'architecture', candRel, outRel,
      '--repo-root', ROOT, '--quality', 'showcase', '--json'], { cwd: ROOT, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
  } catch (e) {
    console.log((e.stdout || e.message).slice(0, 4000));
    process.exit(1);
  }
  const receipt = JSON.parse(res);
  console.log(JSON.stringify({ ok: receipt.ok, gates: receipt.gates, head: head && head.slice(0, 7), states: applied }));
  if (!receipt.ok) {
    console.log(JSON.stringify(receipt.diagnostics || receipt, null, 2).slice(0, 4000));
    process.exit(1);
  }
}

main();
