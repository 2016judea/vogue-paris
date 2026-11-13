// Full-resolution cover JPEGs for /board (Aidan, 2026-11-12: "opens the image in
// super high rez … to copy images for my substack"). JPEG, not WebP, because a
// copied JPEG pastes cleanly into Substack's editor. Source is the same cropped
// scan the reader shows (mirror-reviewed > mirror-crop > mirror-hi), at the
// mirror's native width (~2400px). Uploads to Blob at vogue/<ark>/cover.jpg and
// writes public/data/covers.json { ark: {url, w, h} }. Skips covers already done.
import fs from 'node:fs';
import path from 'node:path';
import sharp from 'sharp';
import { put } from '@vercel/blob';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
for (const line of fs.readFileSync(path.join(ROOT, '.env.local'), 'utf8').split('\n')) {
  const m = line.match(/^(\w+)=(.*)$/); if (m) process.env[m[1]] = m[2];
}
const issues = JSON.parse(fs.readFileSync(path.join(ROOT, 'public/data/issues.json')));
const outPath = path.join(ROOT, 'public/data/covers.json');
const out = fs.existsSync(outPath) ? JSON.parse(fs.readFileSync(outPath)) : {};
const pad = n => String(n).padStart(3, '0');

let i = 0;
await Promise.all(Array.from({ length: 6 }, async () => {
  while (i < issues.length) {
    const it = issues[i++];
    if (!it.ready || out[it.ark]) continue;
    const f = `p${pad(it.first)}.jpg`;
    const src = ['mirror-reviewed', 'mirror-crop', 'mirror-hi']
      .map(d => path.join(ROOT, d, it.ark, f)).find(p => fs.existsSync(p));
    if (!src) { console.warn('no source', it.ark, f); continue; }
    const { data, info } = await sharp(src).rotate().jpeg({ quality: 92, mozjpeg: true }).toBuffer({ resolveWithObject: true });
    const r = await put(`vogue/${it.ark}/cover.jpg`, data, {
      access: 'public', addRandomSuffix: false, allowOverwrite: true,
      contentType: 'image/jpeg', cacheControlMaxAge: 31536000,
    });
    out[it.ark] = { url: r.url, w: info.width, h: info.height };
    console.log(it.date, info.width + 'x' + info.height);
  }
}));
fs.writeFileSync(outPath, JSON.stringify(out));
console.log(Object.keys(out).length, 'covers');
