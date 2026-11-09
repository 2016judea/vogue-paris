// Convert mirrored Gallica pages to WebP, upload them to Vercel Blob, and rebuild
// public/data/issues.json. Safe to run repeatedly: an issue is uploaded once,
// after the mirror marks it DONE, and recorded in data/uploaded.json.
//
// Two tiers per page, so a phone never pulls the desktop file:
//   w1200 — phone and laptop
//   w2400 — desktop retina and pinch-zoom (the mirror's own resolution)
import fs from 'node:fs';
import path from 'node:path';
import sharp from 'sharp';
import { put } from '@vercel/blob';
import { execFileSync } from 'node:child_process';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
for (const line of fs.readFileSync(path.join(ROOT, '.env.local'), 'utf8').split('\n')) {
  const m = line.match(/^(\w+)=(.*)$/); if (m) process.env[m[1]] = m[2];
}
const MIRROR = path.join(ROOT, 'mirror-hi');  // 2400px copies (was mirror/ at 1600px)
const seed = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/issues_seed.json')));
const upPath = path.join(ROOT, 'data/uploaded.json');
const uploaded = fs.existsSync(upPath) ? JSON.parse(fs.readFileSync(upPath)) : {};
// w1200: phones (390 css px at 3x) and small laptops; w2400: desktop retina and pinch-zoom.
const TIERS = [['w1200', 1200, 74], ['w2400', 2400, 78]];
const pad = n => String(n).padStart(3, '0');

async function pool(items, n, fn) {
  let i = 0;
  await Promise.all(Array.from({ length: n }, async () => { while (i < items.length) await fn(items[i++]); }));
}

for (const it of seed) {
  const dir = path.join(MIRROR, it.ark);
  if (it.exclude || fs.existsSync(path.join(MIRROR, it.ark, 'BOUND'))) continue;
  if (uploaded[it.ark]?.hi || !fs.existsSync(path.join(dir, 'DONE'))) continue;
  // it.start is the cover page checked by eye for bound volumes; never begin before it.
  const all = fs.readdirSync(dir).filter(f => /^p\d{3}\.jpg$/.test(f) && +f.slice(1, 4) >= it.start).sort();
  const labels = JSON.parse(fs.readFileSync(path.join(dir, 'manifest.json'))).pages.map(p => String(p.label || ''));
  // Bound volumes open on the binding board, marbled endpapers and blank leaves
  // before the cover (2026-11-08: 15 juin 1920 had ten such pages). Trim them,
  // and the same at the back, so an issue opens on its cover.
  const junk = async f => {
    const n = +f.slice(1, 4);
    if (/plat|garde|dos|reliure/i.test(labels[n - 1] || '')) return true;
    const { data } = await sharp(path.join(dir, f)).resize(64, 80, { fit: 'fill' }).greyscale().raw().toBuffer({ resolveWithObject: true });
    // Judge the middle of the leaf only: a blank endpaper photographed with the
    // dark binding strip at its edge otherwise reads as a busy page (01 juillet 1920).
    let s = 0, s2 = 0, hi = 0, c = 0;
    for (let y = 12; y < 68; y++) for (let x = 10; x < 54; x++) {
      const v = data[y * 64 + x]; s += v; s2 += v * v; if (v > 200) hi++; c++;
    }
    const mean = s / c, sd = Math.sqrt(s2 / c - mean * mean), frac = hi / c;
    return sd < 14 || (frac < 0.25 && sd < 30);
  };
  let a = 0, z = all.length - 1;
  while (a < z && await junk(all[a])) a++;
  while (z > a && await junk(all[z])) z--;
  const files = all.slice(a, z + 1);
  const coverN = +files[0].slice(1, 4);
  // Crop each scan to the physical page and level it (scripts/crop.py): Gallica's
  // photos show the scanner bed, gutter and neighbouring leaves around the page.
  const cropDir = path.join(ROOT, 'mirror-crop', it.ark);
  if (!fs.existsSync(path.join(cropDir, 'DONE'))) {
    execFileSync(path.join(ROOT, '.venv/bin/python'), [path.join(ROOT, 'scripts/crop.py'), '--dir', dir, cropDir], { stdio: 'inherit' });
    fs.writeFileSync(path.join(cropDir, 'DONE'), '');
  }
  let base = null, w = 0, h = 0;
  await pool(files, 6, async f => {
    const n = +f.slice(1, 4);
    const src = fs.existsSync(path.join(cropDir, f)) ? path.join(cropDir, f) : path.join(dir, f);
    for (const [tier, width, q] of TIERS) {
      const buf = await sharp(src).resize({ width, withoutEnlargement: true }).webp({ quality: q }).toBuffer();
      const r = await put(`vogue/${it.ark}/${tier}/p${pad(n)}.webp`, buf, {
        access: 'public', addRandomSuffix: false, allowOverwrite: true,
        contentType: 'image/webp', cacheControlMaxAge: 31536000,
      });
      if (!base) base = r.url.split('/vogue/')[0];
    }
    if (n === coverN) {
      const meta = await sharp(src).metadata(); w = meta.width; h = meta.height;
      // the wall's cover thumbnail, from the full-resolution scan
      fs.mkdirSync(path.join(ROOT, 'public/covers'), { recursive: true });
      await sharp(src).resize({ width: 480 }).webp({ quality: 74 }).toFile(path.join(ROOT, 'public/covers', it.ark + '.webp'));
    }
  });
  const nums = files.map(f => +f.slice(1, 4));
  uploaded[it.ark] = { base, first: Math.min(...nums), last: Math.max(...nums), w, h, hi: true, tiers: TIERS.map(t => [t[0], t[1]]) };
  fs.writeFileSync(upPath, JSON.stringify(uploaded, null, 1));
  console.log('uploaded', it.date, it.ark, files.length, 'pages');
}

// Issues whose scan has no cover (opens on text or an ad) are left off the site.
const out = seed.filter(it => !it.exclude && !fs.existsSync(path.join(MIRROR, it.ark, 'BOUND'))).map(it => {
  const u = uploaded[it.ark];
  return u
    ? { ...it, ready: true, base: u.base, first: u.first, last: u.last, ar: +(u.w / u.h).toFixed(4), tiers: u.tiers || [['w800', 800], ['w1600', 1600]], en: fs.existsSync(path.join(ROOT, 'public/text', it.ark + '.json')) }
    : { ...it, ready: false };
});
fs.mkdirSync(path.join(ROOT, 'public/data'), { recursive: true });
fs.writeFileSync(path.join(ROOT, 'public/data/issues.json'), JSON.stringify(out));
console.log('issues.json:', out.filter(x => x.ready).length, 'of', out.length, 'ready');
