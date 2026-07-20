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

## The "3D Map" tab

A third tab that lays out the whole collection on one floor — every owned set gets a grid slot — and drops you into it with a free-roam camera (click to look around, WASD to move, Space/Shift for up/down) instead of the single-set modal's orbit-around-one-object view. Implementation: `public/lego3dmap.js`.

**Why a different camera scheme than the single-set viewer.** `OrbitControls` (used in the single-set modal) orbits around one fixed point — the right model for "inspect this one set," wrong for "walk around a whole room of them." The map uses `PointerLockControls` (mouse-look, click-to-lock — the standard first-person "explore a 3D space" pattern) plus hand-rolled WASD/Space/Shift movement, giving genuine free 3D movement rather than orbiting a point or being confined to a walking plane.

**Layout and fallback.** Sets are placed on a square grid (`CELL_SIZE = 500` LDraw units apart) sized to `⌈√n⌉` columns. Every set gets a placeholder immediately — a small standee card textured with its product photo — regardless of whether it has an LDraw model, so the whole collection is represented from the first frame. Sets with a cached OMR model swap from placeholder to real geometry as their model loads, using one shared `LDrawLoader` (and one shared material/parts fetch) across every model in the scene, so parts common to multiple sets are only ever fetched once.

**Data flow.** Opening the tab fetches `/api/collection` (what to place) and `GET /api/collection/ldraw-models` (a bulk, cache-only lookup — one query for every owned set's known model, added specifically so a returning visit doesn't cost N round trips). Sets missing from that bulk result get checked individually in the background, a few at a time, purely to warm the cache for next visit — not awaited, and never shows an error toast, since the user didn't ask for those specific checks.

**A real bug this surfaced and fixed:** the first version awaited the shared `preloadMaterials()` fetch *before* adding any placeholders to the scene — meaning a slow or stuck network fetch (a real risk given the OMR/parts-library reachability caveats above) left the entire map blank, not just the 3D models. Fixed by decoupling them: placeholders (which need no network access beyond an already-loading photo) go up synchronously and the render loop starts immediately; real LDraw models load in afterward and swap in over their placeholder whenever they're ready, however long that takes.

**Known v1 limitations, not fixed:**
- Fixed grid spacing — a very large modeled set can outgrow its cell and overlap a neighbor. Packing slot size to each model's real footprint would mean loading before layout, delaying first paint.
- No state preservation across tab switches — leaving the map tab disposes the WebGL context and camera position; returning rebuilds from scratch.
- No distance-based loading/culling — every set with a cached model loads at once. Fine for the collection sizes this was tested with (single digits to a few dozen); a very large, heavily-OMR-covered collection could get slow. LOD-by-camera-distance would be the fix, not implemented.
- Product-photo textures on placeholder cards depend on the image host sending permissive-enough CORS behavior for WebGL texture use; if a given photo fails for that reason, that one card falls back to a plain color rather than breaking the scene (verified: this fallback path itself was exercised and works — not that the CORS behavior of the photo host was verified either way).

**Verified:** the full scene assembly (placeholders, grid layout, labels, shared loader wiring), the immediate-render-then-progressive-model-load fix above, and the tab lifecycle (dispose on leaving, clean rebuild on return) — all confirmed by directly inspecting the rendered scene graph and pixels, not just assumed from the code. Pointer lock itself was confirmed to actually engage/disengage in a real test run; fully driving WASD movement *while* locked wasn't drivable through Playwright's synthetic input in this sandbox (a documented category of headless-browser limitation around the Pointer Lock API, since it's tied to real OS-level mouse capture) — this doesn't affect real users, since browsers guarantee Escape releases the lock at a level no page script can override.
