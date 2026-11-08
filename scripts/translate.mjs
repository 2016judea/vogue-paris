// Translate an issue to English, free and on-device:
//   1. OCR each page with Apple Vision (bin/ocr, built from scripts/ocr.swift)
//   2. put the lines in reading order (full-width lines split the page into
//      bands; inside a band, columns are read left to right)
//   3. translate with an open-source model through Ollama (gemma3:12b)
// Writes public/text/<ark>.json: { "<page>": { "fr": "...", "en": "..." } }.
// Resumable: pages already in the file are skipped.
// Usage: node scripts/translate.mjs <ark> [<ark> ...]   (or --all)
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const MODEL = process.env.MODEL || 'gemma3:12b';
const uploaded = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/uploaded.json')));
const seed = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/issues_seed.json')));
const MIN_CHARS = 60;     // less than this is a brand name or a caption stub: not worth a toggle
const CHUNK = 2500;       // characters per model call; longer inputs got truncated by the 4b model

function ocr(file) {
  const out = execFileSync(path.join(ROOT, 'bin/ocr'), [file], { encoding: 'utf8', maxBuffer: 1 << 24 });
  return out.split('\n').filter(Boolean).map(l => JSON.parse(l)).filter(l => l.t.trim());
}

function readingOrder(lines) {
  lines.sort((a, b) => a.y - b.y);
  const bands = [[]];
  for (const l of lines) {
    if (l.w > 0.55) { bands.push([l]); bands.push([]); } else bands[bands.length - 1].push(l);
  }
  const out = [];
  for (const band of bands) {
    if (!band.length) continue;
    // columns: cluster by left edge
    const cols = [];
    for (const l of [...band].sort((a, b) => a.x - b.x)) {
      const c = cols.find(c => Math.abs(c.x - l.x) < 0.12);
      if (c) c.lines.push(l); else cols.push({ x: l.x, lines: [l] });
    }
    cols.sort((a, b) => a.x - b.x);
    for (const c of cols) out.push(...c.lines.sort((a, b) => a.y - b.y));
  }
  // rejoin words hyphenated across lines
  let text = '';
  for (const l of out) {
    const t = l.t.trim();
    if (text.endsWith('-') && /^[a-zà-ÿ]/.test(t)) text = text.slice(0, -1) + t;
    else text += (text ? '\n' : '') + t;
  }
  return text;
}

async function translate(fr) {
  const parts = [];
  let buf = '';
  for (const para of fr.split('\n')) {
    if (buf.length + para.length > CHUNK && buf) { parts.push(buf); buf = ''; }
    buf += (buf ? '\n' : '') + para;
  }
  if (buf) parts.push(buf);
  const en = [];
  for (const p of parts) {
    const prompt = `You are translating a page of French Vogue (Paris edition, 1920s–1950s) into English.
The text below came from OCR, one printed line per line. Lines broken mid-sentence belong together.
Translate ALL of it into natural, elegant English in the magazine's period tone. Do not skip or summarise anything.
Join broken lines into proper paragraphs. Keep names of couturiers, shops, people and places as they are.
"Mode" means fashion. Output only the English text, no notes, no markdown.

${p}`;
    const r = await fetch('http://localhost:11434/api/generate', {
      method: 'POST',
      body: JSON.stringify({ model: MODEL, prompt, stream: false, options: { temperature: 0.2, num_ctx: 8192 } }),
    });
    const j = await r.json();
    en.push(String(j.response || '').trim().replace(/\*/g, ''));
  }
  return en.join('\n\n');
}

const arks = process.argv.includes('--all')
  ? seed.filter(s => !s.exclude && uploaded[s.ark]?.hi).map(s => s.ark)
  : process.argv.slice(2);

for (const ark of arks) {
  const u = uploaded[ark];
  if (!u) { console.log('not uploaded yet', ark); continue; }
  const outFile = path.join(ROOT, 'public/text', ark + '.json');
  const done = fs.existsSync(outFile) ? JSON.parse(fs.readFileSync(outFile)) : {};
  const t0 = Date.now();
  for (let n = u.first; n <= u.last; n++) {
    const key = String(n - u.first + 1);   // the reader's page number, 1 = cover
    if (key in done) continue;
    const file = path.join(ROOT, 'mirror-hi', ark, `p${String(n).padStart(3, '0')}.jpg`);
    if (!fs.existsSync(file)) continue;
    const fr = readingOrder(ocr(file));
    done[key] = fr.replace(/\s+/g, '').length < MIN_CHARS ? null : { fr, en: await translate(fr) };
    fs.writeFileSync(outFile, JSON.stringify(done));
    process.stdout.write(`\r${ark} page ${key}/${u.last - u.first + 1}`);
  }
  console.log(`\n${ark} done in ${Math.round((Date.now() - t0) / 1000)}s`);
}
