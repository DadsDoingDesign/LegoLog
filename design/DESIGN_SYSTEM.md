# LegoLog Design System

Implementation of `design/BRAND_GUIDE.md`, applied to fix the issues found in `design/WEBSITE_AUDIT.md` and `design/USABILITY_AUDIT.md`.

- **Source:** `public/design-system.css` — tokens, reset, and components, ~350 lines, zero build step.
- **Live showcase:** `public/style-guide.html` — every token and component rendered on one page.
- **Applied in:** `public/index.html` (the real app), replacing the previous Tailwind CDN–based markup.

## Why hand-written CSS instead of Tailwind

The previous build loaded Tailwind from `cdn.tailwindcss.com` at runtime — Tailwind's own docs call that pattern development-only, and it was reproducibly unreachable in this audit (`curl -I` → `403`), which meant the entire UI had no styling at all when it happened (see Website Audit, Critical finding). Two ways to fix that: compile Tailwind to a static file, or write the actual (small) set of styles this app needs by hand. Given the whole product is one 350-line HTML file with no build pipeline (README's deploy story is literally "push `public/index.html` to Vercel's CDN"), adding a Node/Tailwind build step would be a bigger tooling change than the design ask called for. A hand-written stylesheet keeps the project's zero-build-step deploy model intact, is smaller than a compiled Tailwind bundle would be, and — most importantly — has **no runtime dependency on anything external**.

## Tokens

All tokens are CSS custom properties on `:root` in `design-system.css`. Reference the file directly for exact values; the categories:

| Category | Tokens | Notes |
|---|---|---|
| Neutrals | `--color-bg`, `--color-surface`, `--color-surface-raised`, `--color-surface-hover`, `--color-border`, `--color-border-strong`, `--color-text`, `--color-text-muted`, `--color-text-faint` | `--color-text-faint` (slate-500) is documented as decorative-only — it fails AA for body copy (Website Audit #1). Everything a user needs to read uses `--color-text-muted` or `--color-text`. |
| Brand accents | `--color-primary(-hover/-ink)`, `--color-danger(-strong)`, `--color-info`, `--color-success(-strong)` | The "brick four." Primary (yellow) is the only one used decoratively; the other three are semantic (danger/info/success) — see Brand Guide §3.1. |
| Type | `--font-body`, `--font-display` | `--font-display` is a zero-dependency `ui-rounded` stack (see below) rather than the webfont floated in the brand guide's initial direction — same rationale as the CSS decision above: don't reintroduce an external request right after removing one. |
| Spacing | `--space-1` … `--space-8` | 4px base unit, matches what the previous Tailwind-based build already used — no visual change, now just named. |
| Radius | `--radius-sm/md/lg/full` | |
| Elevation | `--shadow-md`, `--shadow-lg` | Used on the search dropdown and modal only — this UI is flat by default, shadow means "floating above the page." |
| Focus | `--focus-ring` | A 2px yellow ring with a background-color gap, applied via `:focus-visible` (mouse clicks don't trigger it, keyboard nav does) — fixes Website Audit #2 / Usability #6. |

**On the display font:** the brand guide's direction (§4) was a self-hosted rounded webfont (Baloo 2/Fredoka). This implementation uses `ui-rounded` — a CSS generic that resolves to SF Pro Rounded on Apple platforms and falls back to the system sans stack everywhere else — instead. Reasoning: adding a Google Fonts `<link>` right after fixing the Tailwind-CDN single-point-of-failure would reintroduce the same class of risk for the sake of a headline font. `ui-rounded` gets most of the "friendly, brick-geometry-adjacent" character on ~60% of traffic (Apple devices) with zero network requests and zero risk. Self-hosting an actual webfont file remains a fine follow-up if the brand wants 100% cross-platform consistency later — flagged in "Not done" below.

## Components

Defined once in `design-system.css`, used everywhere the pattern repeats — no ad hoc one-off styles in `index.html` beyond layout (`style="margin-top:..."` etc., which is intentionally left inline for one-off spacing rather than inventing single-use classes):

| Component | Classes | Where it's used |
|---|---|---|
| Buttons | `.btn` + `.btn-primary` / `.btn-secondary` / `.btn-ghost`, `.btn-sm` | Add, Load more, Reset filters |
| Icon buttons | `.icon-btn`, `.icon-btn-ghost` | Quantity ± steppers, remove, modal close, toast dismiss — all now carry `aria-label`s (Website Audit #4) |
| Form controls | `.input`, `.select`, `.search-input`, `.range`, `.checkbox`, `.field`, `.checkbox-field` | Search box, all Buildable-tab filters |
| Card | `.card` | Collection rows, buildable-set tiles, filter bar container |
| Tabs | `.tabs[role=tablist]`, `.tab[role=tab]` | Now a real ARIA tabs pattern — arrow-key navigation, roving `tabindex`, `aria-selected` driving the active-state style instead of a hand-built class string (Usability finding #6) |
| Badge | `.badge`, `.badge-success`, `.owned-tag` | "✓ own N" in search results |
| Progress | `.progress`, `.progress-fill`, `.is-complete` | Buildable-set coverage bars |
| Modal | `.modal-backdrop`, `.modal[role=dialog]`, `.modal-close`, `.modal-header`, `.modal-body` | Missing-parts modal — now has dialog semantics, a visible close button, and a JS-driven focus trap + focus-return (Website Audit #3, Usability #3/#6) |
| Data table | `.data-table`, `.color-chip` | Missing-parts breakdown |
| Toast | `.toast-region`, `.toast`, `.toast-danger`, `.toast-action` | New — see below |
| Empty state | `.empty-state`, `.headline` | Collection-empty, buildable-empty |

## Behavior changes that shipped with the system (not just CSS)

The design system pass also closed the highest-priority items from the usability audit, since a token/component system is only as good as the interactions it's wired into:

1. **Error toasts.** `api()` in `index.html` now shows a toast on any failed request (network error or non-2xx) before rethrowing — every call site gets user-visible error feedback for free, closing Website Audit #7 / Usability finding #2 in one change.
2. **Undo on remove.** Removing a set now shows a 6-second "Removed X · Undo" toast; Undo re-adds the set at its previous quantity. Closes Usability finding #1 (previously an instant, unrecoverable delete).
3. **Reset filters.** One button restores the Buildable tab's six filter controls to their defaults. Closes Usability finding #5.
4. **Modal accessibility.** `role="dialog"`, `aria-modal`, a labelled title, a visible close button, a focus trap, and focus-return to whatever triggered the modal. Closes Website Audit #3.
5. **Clamped min-parts input.** No more silently-broken queries from an out-of-range value. Closes Usability finding #8.
6. **`/` focuses search**, arrow keys move between tabs — small power-user affordances the audit flagged as missing for the app's own target user (Usability, "Flexibility and efficiency").
7. **Broken images degrade instead of vanishing** — `onerror` now swaps to a small inline placeholder icon (a miniature stud mark, on-brand) instead of `visibility:hidden`, closing Website Audit #8.
8. **Favicon** — the stud mark, shipped as an inline SVG data URI (`<link rel="icon">`), plus `theme-color` and a real `<meta name="description">`. Closes Website Audit #6 (partially — see "Not done").

## Not done (flagged, not fixed, in this pass)

Kept out of scope to avoid ballooning a design-system pass into a full rewrite — listed so they're not lost:

- **`apple-touch-icon` / `manifest.json`** — needs real PNG assets exported from the SVG mark; an SVG favicon covers modern desktop/Android browsers but iOS home-screen icons specifically want a PNG. Small follow-up.
- **Full ARIA combobox pattern on search** (`role="combobox"`, `aria-activedescendant`, arrow-key result navigation). The current search dropdown is a plain, unlabelled list — better than a half-correct ARIA pattern with mismatched roles, but not a complete accessible combobox. Worth a dedicated pass rather than bolting on partial semantics here.
- **Bulk actions / in-collection search & sort** — backlog items from the usability audit's "Flexibility and efficiency" section; real feature work, not a styling change.
- **Self-hosted display webfont** — see tokens section above; `ui-rounded` is the zero-risk placeholder, a real webfont is a brand-fidelity upgrade, not a functional gap.

## How to extend this system

- New colors/spacing/radius → add a token in `:root`, don't hardcode a hex or px value in a component rule.
- New repeating UI pattern → add a component class in `design-system.css`, not a run of one-off utility classes in the HTML — the whole point of moving off Tailwind's utility soup was fewer, more meaningful class names per element.
- Check any new text/background pairing against the contrast rule in `design/BRAND_GUIDE.md` §3.3 before shipping it.
