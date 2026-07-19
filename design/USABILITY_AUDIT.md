# LegoLog Usability Audit

Method: heuristic evaluation (Nielsen's 10 usability heuristics) walking the three real user flows the app supports:

1. **Search → add a set to your collection**
2. **Manage your collection** (adjust quantity, remove a set)
3. **Find what you can build** (filter, open a set's missing-parts breakdown, act on fill suggestions)

This is a companion to `design/WEBSITE_AUDIT.md`, which covers visual/technical issues (contrast, focus states, ARIA). This document covers *interaction and flow* — what happens when a real person tries to get something done. Overlapping accessibility items (modal semantics, icon-button labels) are only cross-referenced here, not repeated in full.

## Priority findings

| # | Heuristic | Severity | Finding |
|---|---|---|---|
| 1 | Error prevention / User control | **High** | Removing a set (✕) and decrementing quantity to 0 both delete instantly — **no confirmation, no undo**. A misclick permanently drops a set from the collection. |
| 2 | Help users recover from errors | **High** | No API call in the entire app surfaces a failure to the user (see Website Audit #7). Add/remove/quantity-change/modal-load all fail silently on a network error. |
| 3 | Visibility of system status | **Medium** | Mutating actions (add, qty ±, remove) give no pending/loading state and aren't disabled mid-request — fast double-clicks can fire duplicate requests, and there's no success confirmation beyond the list re-rendering. |
| 4 | Flexibility / efficiency | **Medium** | No bulk remove, no search/sort/filter *within* the collection you've already built, no keyboard shortcut to focus search — friction that scales badly for the app's own target user (a "serious collector" with 50+ sets). |
| 5 | Recognition over recall | **Medium** | No "reset filters" control on the Buildable tab — six independent filter controls with no single way back to defaults. |
| 6 | Consistency / standards | **Medium** | Tabs are visually tab-like but don't follow the ARIA tabs pattern (no arrow-key navigation between them); see Website Audit #3 for the modal's missing dialog semantics. |
| 7 | Help and documentation | **Low** | Domain jargon ("coverage," "lots") is correct for the target audience but unexplained anywhere — fine for a returning user, a rough edge for a cold/shared link. |
| 8 | Error prevention | **Low** | "Min parts" number input isn't clamped client-side (`min=1` is an unenforced attribute here since the value is read raw) — an edge-case value produces a confusing empty result with no explanation. |

## By heuristic

### 1. Visibility of system status — Partial
**Working well:** the buildable-count label switches to "computing…" during a filter query, and the coverage slider's live label updates on drag. That's the right pattern — keep it.

**Gaps:** none of the collection-mutation actions (add / ± quantity / remove) show any pending state. Combined with no debounce or disabled-while-pending guard, a fast double-click on ± or the remove button can race two requests against the same row. There's also no toast/confirmation on a *successful* add — the only feedback is the search dropdown closing and the collection list updating somewhere else on the page, which a user has to notice on their own.

### 2. Match between system and the real world — Good
Vocabulary (set number, coverage, lots, spares, theme) matches what a Rebrickable/BrickLink/Brickset user already knows. This is the right call for the audience — don't simplify the language, that would actively work against the "builder's tool" brand personality (Brand Guide §1).

### 3. User control and freedom — Needs work
This is the sharpest finding in the audit. Two destructive paths have zero recovery:

- Click ✕ on any collection row → the set is gone, no confirm dialog, no "undo" toast.
- Click − on a row already at quantity 1 → same deletion path, silently, and it's one click away from the "decrease" action a user reaches for constantly while adjusting counts.

For a data-entry tool where a user's collection is the entire point of the product, an accidental permanent delete is the worst failure mode available. **Recommendation:** don't add a confirmation modal (that's friction on every delete, and this app's brand is "fast, not fussy") — add a 4–5 second **undo toast** instead ("Removed 75192 · Undo"), which solves the recovery problem without slowing down the common case.

The missing-parts modal's only close affordances are Escape and backdrop-click (cross-ref Website Audit #3) — also a control/freedom gap: there's no visible way out for someone who doesn't know either convention.

### 4. Consistency and standards — Mostly good, one structural gap
Button and card patterns are consistent within the app. The gap is structural rather than visual: the tab buttons (`My Collection` / `What Can I Build?`) implement tab *styling* without the tab *interaction pattern* users get elsewhere (arrow-key switching, `role="tablist"`). Low cost to fix, and it's a one-time pattern applied to a component the design system formalizes anyway.

### 5. Error prevention — Partial
**Working well:** search results already show `✓ own N` inline next to sets you've already added, which is exactly the right error-prevention pattern (surfaces relevant state *before* the user acts, instead of after).

**Gap:** the "Min parts" number field has a `min="1"` HTML attribute, but `loadBuildable()` reads `.value` directly into the query string with no clamping — so it's presentation-only, not enforced. Low-frequency edge case, low severity, but a one-line fix (`Math.max(1, +val || 1)`) is worth folding into the design-system pass.

### 6. Recognition rather than recall — Partial
The missing-parts table (have / need / short columns, color swatches) is a strong recognition-over-recall pattern — a user doesn't need to remember what they own, it's laid out next to what's needed. Keep this pattern, extend it (Design System spec reuses it for the color-chip component).

The gap is on the Buildable tab's filter bar: six controls (coverage, min-parts, theme, sort, ignore-color, include-owned) have no visible "current vs. default" indicator and no one-click reset. A user who's been tweaking filters for a few minutes has to recall and manually revert each control individually to get back to a clean baseline.

### 7. Flexibility and efficiency of use — Gap for the target user specifically
LegoLog's own pitch (README) is aimed at collectors with real inventories — the buildability engine only gets interesting once someone has enough sets logged for cross-set coverage to matter. That's exactly the user for whom these are missing:

- No multi-select / bulk remove from the collection.
- No search, sort, or filter *within* the collection list itself (only the *add* search box exists; once a set is in your collection, the only way to find it again in a long list is to scroll and read).
- No keyboard shortcut to jump to search (a `/`-to-focus pattern, standard in dense data tools this app is positioned alongside — GitHub, Linear, etc.).

None of these block a small collection. All three become real friction once a user's collection is large enough for the app's core feature (buildability across sets) to be worth using at all.

### 8. Aesthetic and minimalist design — Good, with one exception
The overall information density is appropriate for the tool's audience — this shouldn't be simplified further, that would hide data the target user actually wants (part-level breakdowns, coverage percentages). The one exception is the Buildable filter bar's mobile behavior (cross-ref Website Audit #9) — six-plus controls wrapping unevenly is a minimalism failure specifically at narrow widths, not at desktop.

### 9. Help users recognize, diagnose, and recover from errors — Weak
There is currently no path from "a request failed" to "the user knows what happened." `api()` throws; almost nothing catches it. Concretely: if `/api/collection` POST fails (Turso cold-start, rate limit, offline), clicking "+ Add" does *nothing visible* — no error state, no retry affordance, nothing in the console a non-developer would ever see. This is the single highest-leverage fix in this audit relative to its cost: one shared error-toast pattern, wired into the existing `api()` helper's catch path, fixes it everywhere at once rather than needing per-call handling.

### 10. Help and documentation — Appropriately minimal, one small gap
The empty-state copy (Brand Guide §6) already does the right amount of "documentation" for a tool this focused — resist the urge to add a tour or onboarding flow, it doesn't fit the brand. The only real gap: a first-time visitor to the Buildable tab with jargon like "coverage" and "lots" has no inline explanation. A single `title` tooltip or a one-line caption under the tab header would close this without adding any onboarding weight.

## Priority for the design-system pass

Ordered by (severity × fix cost) — cheapest, highest-impact fixes first:

1. Wire `api()`'s failures into a shared error-toast component (fixes finding #2 everywhere at once).
2. Add an undo toast on remove / quantity-to-zero, replacing the instant silent delete (finding #1).
3. Add `role="dialog"` + `aria-modal` + a visible close button + focus trap to the missing-parts modal (finding #6 in Website Audit, finding #3 here).
4. Add a "Reset filters" text button to the Buildable filter bar (finding #5).
5. Clamp the min-parts input; add `role="tablist"`/`role="tab"` to the nav (findings #6, #8 above).
6. Backlog (not urgent, but worth a card): bulk remove, in-collection search/sort, `/`-to-focus.
