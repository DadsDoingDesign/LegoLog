# LegoLog

Track the LEGO sets you own (with quantities) and find out **which other sets you
could build** from the combined pool of parts — powered by the
[Rebrickable database dumps](https://rebrickable.com/downloads/).

Runs on [Vercel](https://vercel.com) (FastAPI as a Python serverless function) with
[Turso](https://turso.tech) (hosted libSQL/SQLite) as the database — Vercel functions
are stateless with a read-only filesystem, so the catalog and your collection both
live in Turso rather than a bundled `.db` file.

## Set up the database (one-time)

1. Build the catalog locally:
   ```powershell
   py -3.10 -m pip install -r requirements.txt
   py -3.10 import_data.py --download     # ~16 MB download, ~30 s import -> legolog.db
   ```
2. In the [Turso dashboard](https://dashboard.turso.tech), create a database and an
   auth token for it (Database → Connect / Create Token).
3. Copy `.env.example` to `.env` and fill in `TURSO_DATABASE_URL` and
   `TURSO_AUTH_TOKEN` from step 2 (`.env` is gitignored).
4. Push the catalog to Turso:
   ```powershell
   py -3.10 push_to_turso.py     # only pushes tables app.py queries, ~20-30 min over the network
   ```
   This only pushes `themes`, `colors`, `parts`, `sets`, `set_parts`, `set_totals` —
   the raw Rebrickable inventory tables aren't needed at runtime — and skips
   gear/books/parts-pack sets since those are excluded from results anyway.
   `owned_sets` is created if missing but never overwritten, so re-running this
   after a catalog refresh doesn't touch your collection.

## Run locally

```powershell
py -3.10 -m uvicorn app:app --port 8100
# open http://localhost:8100
```

## Deploy to Vercel

1. Push this repo to GitHub and import it in Vercel (or `vc deploy` from the CLI) —
   Vercel auto-detects the FastAPI app at `app.py`.
2. In the Vercel project's Environment Variables settings, add `TURSO_DATABASE_URL`
   and `TURSO_AUTH_TOKEN` (same values as your local `.env`).
3. `public/index.html` is served straight from Vercel's CDN; everything else routes
   through the one Python function (`vercel.json` sets `maxDuration: 60`, though the
   Hobby plan hard-caps functions at 10s regardless — the `/fill` endpoint's gap-recommendation
   queries are the ones most likely to bump into that on a free plan).

## How it works

- `import_data.py` loads the Rebrickable CSVs into a local `legolog.db` (SQLite) and
  precomputes `set_parts`: for every set, the parts required to build it —
  latest inventory version, **minifigs expanded into their parts**, spare parts
  tracked separately (spares count toward what you *own*, not what a set *needs*).
  This local file is a build artifact (gitignored) — `push_to_turso.py` is what
  actually populates the database the app reads from.
- `db.py` is a thin libSQL connection layer with a `sqlite3.Row`-like wrapper (rows
  addressable by name *or* index) so the rest of the app's SQL didn't need to change
  when it moved off local SQLite.
- Your collection lives in Turso's `owned_sets` table and **survives catalog
  refreshes** — re-run `import_data.py --download` then `push_to_turso.py` any time
  to pick up Rebrickable's latest dumps.
- The buildability engine pools every part you own
  (`sum over owned sets × quantity, spares included`) and compares it against the
  requirements of all buildable sets in one SQL pass, cached per warm instance until
  your collection changes.

## Features

- Search by set number or name, add with quantity (own multiples? bump the counter).
- **What Can I Build?** tab: coverage slider (100% = fully buildable, lower it to
  see near-misses), min-parts filter, theme filter, sort by coverage / part count / year.
- **Ignore color** toggle: match on part shape only.
- Click any result to see exactly which parts you're missing (with color swatches
  and have/need counts) — doubles as a BrickLink shopping list.
- **Gap-fill suggestions**: the same modal recommends sets to buy — single sets
  that cover everything missing, then pairs; when nothing can reach 100% (some
  parts are exclusive to one set), it shows the closest pairings with combined %.
- Parts packs, gear, and books are excluded from buildable results (theme
  branches listed in `EXCLUDED_THEME_NAMES` in `app.py`).
- Sets you own are excluded from results by default ("Include sets I own" to show them).

## API

| Endpoint | What |
|---|---|
| `GET /api/search?q=` | find sets |
| `GET/POST /api/collection`, `PUT/DELETE /api/collection/{set_num}` | manage owned sets |
| `GET /api/buildable?min_coverage=&min_parts=&theme_id=&ignore_color=&include_owned=&sort=` | the engine |
| `GET /api/sets/{set_num}/missing?ignore_color=` | missing-parts breakdown |
| `GET /api/sets/{set_num}/fill?ignore_color=` | buy-suggestions (singles / pairs / near-pairs) |
| `GET /api/themes` | theme list |

## Notes / future ideas

- Part matching is exact on `(part_num, color)` — no mold-variant or alternate-part
  substitution yet (`part_relationships.csv` would enable that).
- Data © Rebrickable — thanks!

## Design system

`public/index.html` is styled entirely by `public/design-system.css` — a small,
self-hosted, zero-build-step stylesheet (no CDN, no compile step). Browse every
token and component at `public/style-guide.html`. Full writeup — brand guide,
a design/usability audit of the previous build, and the system's rationale —
lives in `design/`:

- [`design/BRAND_GUIDE.md`](design/BRAND_GUIDE.md)
- [`design/WEBSITE_AUDIT.md`](design/WEBSITE_AUDIT.md)
- [`design/USABILITY_AUDIT.md`](design/USABILITY_AUDIT.md)
- [`design/DESIGN_SYSTEM.md`](design/DESIGN_SYSTEM.md)

Each set also has a **View in 3D** button — renders a community-built LDraw
model of the set in-browser (three.js + LDrawLoader) when one exists on
[LDraw.org's Official Model Repository](https://library.ldraw.org/omr), falling
back to the product photo otherwise. See
[`design/3D_VIEWER.md`](design/3D_VIEWER.md) for how it works and — important —
which parts of it are verified vs. best-effort.
