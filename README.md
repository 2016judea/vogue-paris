# Vogue Paris

**Live:** https://vogue-paris.vercel.app

Every issue of French Vogue that the BnF has digitised on Gallica (231 issues, 1920–1954), as a cover wall and a page-by-page reader modelled on the GLEAN reader (readglean.com/issue-02).

## How it works

- `public/index.html` is the cover wall (ported from the "Vogue Paris Covers" artifact). Tap a cover to read.
- `public/issue.html` is the reader, served at `/issue/<ark>`.
- `public/board.html` (`/board`) puts every cover on one grid; tap one for the full-res JPEG (`scripts/covers_full.mjs`, Blob `vogue/<ark>/cover.jpg`) with a Copy button for pasting into Substack.
- `public/data/issues.json` lists every issue and whether its pages are uploaded.
- Page scans live in Vercel Blob (`vogue-paris-pages`), two widths per page: `w800` and `w1600`.

## Why the pages are mirrored, not linked

Gallica sits behind Cloudflare. It blocks curl and `HeadlessChrome` user agents, and it blocks its images when they're embedded from another site. A headless Chrome with a normal user agent, fetching from a gallica.bnf.fr tab, gets through. It throttles bursts, so the mirror fetches 3 pages at a time and backs off when it gets an HTML page instead of an image.

## Scripts

- `scripts/run_mirror.sh` launches headless Chrome and runs `scripts/mirror.js`, which copies every page at 1600px into `mirror/` (gitignored). It's resumable.
- `scripts/sync.mjs` trims binding boards and blank endpapers, converts the rest to WebP, uploads to Blob, writes the cover thumbnails, and rebuilds `issues.json`. Needs `BLOB_READ_WRITE_TOKEN` in `.env.local`.
- `scripts/sync_loop.sh` runs sync every 15 minutes and deploys whenever new issues are ready.

Source: gallica.bnf.fr / Bibliothèque nationale de France.
