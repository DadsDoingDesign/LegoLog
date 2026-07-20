# "View in 3D"

A button on each set (collection cards, buildable-set cards) that opens a rotatable 3D render of the set, built from a community-made **LDraw** file — the open format LEGO CAD tools (including BrickLink Studio) read and write — sourced from **LDraw.org's Official Model Repository (OMR)**, a free, CC‑BY-licensed library of LDraw replicas of official LEGO sets.

Why this and not BrickLink Studio directly: Studio (`bricklink.com/v3/studio/download.page`) is a desktop application, not a web API — there's no endpoint a server can call to "look up a set and get a render back." OMR is the actual underlying LDraw data Studio itself would read; three.js's `LDrawLoader` renders it directly in the browser, so no desktop install is needed.

## Architecture

```
Browser                          LegoLog backend (app.py)         Third parties
--------                         -------------------------        -------------
"View in 3D" click
  → GET /api/sets/{n}/ldraw-model  → checked/cached in Turso
                                      (ldraw_models table)     →  library.ldraw.org/omr
                                                                    (best-effort scrape,
                                                                     see caveat below)
  if available:
  → dynamic import('./lego3d.js')
    (three.js + LDrawLoader,
     vendored in public/vendor/,
     only fetched here — not on
     page load)
  → GET /api/sets/{n}/ldraw-model/file → proxies the actual  →  library.ldraw.org
                                          LDraw file through
                                          our own origin
                                          (sidesteps relying
                                          on OMR sending CORS
                                          headers)
  → LDrawLoader fetches individual
    brick geometry as it parses
    the model                                                 →  raw.githubusercontent.com/
                                                                   gkjohnson/ldraw-parts-library
                                                                   (public static mirror of the
                                                                   LDraw parts library, used by
                                                                   three.js's own examples)
```

Falls back to the existing product photo whenever no model is found — OMR is community-built and doesn't cover every set, so "not available" is an expected, common outcome, not an error state.

## What's verified vs. best-effort

Built and tested in a sandboxed dev environment whose network egress policy blocks `library.ldraw.org` and `bricklink.com` outright (not a production concern — Vercel's backend and real users' browsers have no relationship to that sandbox's policy). That constrained what could actually be tested end to end:

**Verified — exercised against real data or the real rendering pipeline:**
- The WebGL scene/camera/renderer/controls setup in `public/lego3d.js`.
- Every `LDrawLoader`/`OrbitControls` method call is checked against the actual installed library source (not written from memory) — `setPartsLibraryPath`, `preloadMaterials`, `loadAsync`, constructor options.
- The import map + dynamic-import wiring (three.js is fetched only when the modal opens, confirmed via network trace).
- The full UI flow: opening the modal, the "no model found" state, the error state, focus trap, Escape/backdrop close, focus return to the triggering button — all exercised through the real `index.html` with a mocked backend.
- The LDraw parts-library CDN mirror (`raw.githubusercontent.com/gkjohnson/ldraw-parts-library`) is real and serves correct data — confirmed by directly fetching `LDConfig.ldr` and sample part files.

**Best-effort, not verified against the live site — check these after deploying:**
- `_lookup_omr_model()` in `app.py`: the OMR search URL (`/omr/sets/?search=`) and the regexes that pull a model-file link out of the result HTML are built from OMR's published file-naming spec and usage docs, not from ever having actually seen a live OMR page (network-blocked in dev). If it's wrong, "View in 3D" will just always report "not available" — it fails closed, never crashes — and the fix is entirely contained to that one function.
- End-to-end reachability of `raw.githubusercontent.com` from a real browser: direct-fetch tests from the dev sandbox got inconsistent results (an immediate clean failure in one run, a hung connection in another) — both attributable to that sandbox's proxy, but it means the full "OMR found something" render path has not been watched complete successfully end to end. Use `GET /api/sets/{set_num}/ldraw-model?refresh=true` to bypass the cache while testing/debugging so repeated attempts don't get stuck on a stale result.

## If the OMR lookup needs adjusting

Everything OMR-specific lives in `_lookup_omr_model()` in `app.py`. It's deliberately isolated from the rest of the feature (caching, the file proxy, and all client-side rendering are independent of it) so fixing the search URL or the result-parsing regex is a one-function change. Clear the cache for a set to force a re-check: `DELETE FROM ldraw_models WHERE set_num = ?`, or pass `?refresh=true` to the lookup endpoint.
