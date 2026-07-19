# LegoLog Website Audit

Scope: `public/index.html` (the entire front end — a single static file with inline `<style>`/`<script>`, served by Vercel's CDN per the README). Audited against the brand guide (`design/BRAND_GUIDE.md`) and general industry practice for the site's category (utility/dashboard tools, per the competitive review).

Method: static read-through of the shipped HTML/CSS/JS, plus a rendered screenshot at desktop (1440×900) and mobile (390×844) viewports via headless Chromium.

## Finding severity key

**Critical** = breaks the product for some real users · **High** = visibly unpolished or fails a real accessibility check · **Medium** = inconsistent but not broken · **Low** = cosmetic polish

---

## 🔴 Critical — the entire visual layer is a single external request

The app loads Tailwind from `https://cdn.tailwindcss.com` (`public/index.html:7`) — no local stylesheet, no fallback. Every class in the file (`bg-slate-950`, `rounded-xl`, etc.) is inert HTML until that one script finishes fetching and running its in-browser JIT compiler.

**This isn't hypothetical** — reproduced live in this audit:

```
$ curl -sI https://cdn.tailwindcss.com
HTTP/1.1 403 Forbidden
```

When that request fails (blocked network, ad-blocker, corporate proxy, DNS filtering like Pi-hole/NextDNS, or the CDN just being slow/down), the page renders as unstyled black-on-white HTML — screenshot below is this exact app, same HTML, CDN unreachable:

*(see `current-desktop.png` / `current-mobile.png` captured during this audit — serif system font, default form controls, no color, no layout — the header, tabs, and filter bar are all just falling back to browser defaults)*

This matches Tailwind's own documentation, which explicitly says the Play CDN (`cdn.tailwindcss.com`) is **"designed for development purposes only, not for production"** — it re-parses and recompiles the entire framework client-side on every page load, and has no offline/degraded fallback.

**Fix:** compile Tailwind to a static CSS file at build/deploy time (or hand-roll the small utility set this page actually uses) and ship it from `public/`, same as `index.html` — zero runtime dependency, and it's also faster (no JIT compile, no extra round trip) even when the CDN *is* up. This is the first thing the new design system (`design/DESIGN_SYSTEM.md`) fixes.

---

## 🟠 High

1. **Contrast failure on muted text.** `text-slate-500` (`#64748B`) on `bg-slate-950`/`bg-slate-900` is used for real content — set metadata (`s.set_num · year · theme`), the "Load more" label context, empty-state subtext — not just decoration. That pairing is **~3.7:1**, under WCAG AA's 4.5:1 minimum for body text. `text-slate-400` (already used elsewhere in the same file) clears it — the fix is a find/replace to one consistent muted-text token, not a new color.
2. **No visible keyboard-focus treatment.** No element in the file defines a `focus-visible` ring. Tab through the header nav, the ± quantity steppers, or the remove (✕) button and there's no custom indicator — keyboard users are relying entirely on whatever the browser's default outline happens to render against a near-black (`#020617`) background, which is inconsistent across browsers and easy to lose track of. WCAG 2.4.7 (Focus Visible) territory.
3. **Modal has no dialog semantics.** `#modal` (`public/index.html:95`) is a plain `<div>` — no `role="dialog"`, `aria-modal="true"`, or label; no focus is moved into it on open or returned to the trigger on close; there's no focus trap, so Tab cycles right out to the page behind it; and the only visible way to close it is an invisible backdrop click (Escape works but isn't discoverable). Screen-reader and keyboard users effectively can't use the missing-parts modal, which is one of the app's three core screens.
4. **Icon-only controls have no accessible name.** The remove button is a bare `✕` glyph (`public/index.html:191`), the quantity steppers are `−`/`+` glyphs — all `<button>` with no `aria-label`. A screen reader announces these as "button" with no indication of what they do.

## 🟡 Medium

5. **`class="dark"` on `<html>` (`public/index.html:2`) is dead code.** Nothing in the file uses Tailwind's `dark:` variant — every dark-theme class is a literal (`bg-slate-950`, not `dark:bg-slate-950`). The class does nothing; it reads as a light/dark toggle was planned and never wired up, which will confuse the next person who touches this file.
6. **No favicon, `apple-touch-icon`, `manifest.json`, or Open Graph tags.** The brand has a distinct mark (the stud grid) that's never exported as an image asset — browser tabs and share links currently show a generic blank icon.
7. **Silent failure on API errors.** `api()` (`public/index.html:106`) throws on a non-OK response, but almost none of its callers (`doSearch`, `addSet`, `changeQty`, `removeSet`, `openMissing`) catch it — a failed request (cold Turso connection, rate limit, network blip) currently fails silently with nothing but a browser-console error; the button just appears to do nothing.
8. **Broken images vanish instead of degrading gracefully.** `onerror="this.style.visibility='hidden'"` (used on every set thumbnail) leaves a blank gap the same size as the image with no placeholder glyph — on a slow/missing Rebrickable image CDN response, cards and search results show empty white boxes with no indication anything is wrong.
9. **Filter bar density on mobile.** The "What Can I Build?" filter row (`public/index.html:56-84`) packs 7 controls (slider, number input, 2 selects, 2 checkboxes, count) into a `flex-wrap` row. It doesn't break, but at 390px it wraps into a tall, uneven stack that pushes the results below the fold — no responsive priority/collapse behavior (e.g., a "Filters" disclosure on small screens).

## 🟢 Low

10. Scrollbar is only styled for WebKit (`::-webkit-scrollbar`, `public/index.html:9`) — Firefox falls back to its default scrollbar, a visible inconsistency next to the otherwise-custom chrome.
11. No `meta name="description"`, no `theme-color` meta — minor polish, matters if/when the app is ever shared or added to a home screen.
12. Numeric stats (`#stats`, coverage %, part counts) use proportional figures, so they visually shift width as values change (e.g., a live-updating counter re-flows neighboring text). `font-variant-numeric: tabular-nums` fixes this in one line.
13. Typographic hierarchy is flat — `<h1>` (wordmark) aside, every heading-like element in the page is `text-sm font-medium` or smaller. Section identity currently depends entirely on the active-tab color state, so a screenshot or shared link mid-scroll gives no textual cue which screen you're looking at.

---

## What's already working (keep as-is)

- The dark neutral base and single-yellow-accent CTA pattern is the right call for this product category (see Brand Guide §1) — don't lighten it up or add more accent colors.
- The stud-grid logo mark is distinctive, small, and legible — good brand asset, just needs to be exported as real icon files (favicon/OG).
- Debounced search (250ms) and cursor-based "Load more" pagination are correct, low-friction patterns for this data volume.
- The missing-parts table's color-swatch pattern (hex chip + name) matches the convention BrickLink/Rebrickable users already know — reuse it, don't reinvent it (currently missing from the search-results list, which shows sets but not part colors — n/a there, just noting the pattern is right where it exists).
- Empty-state copy tone (`design/BRAND_GUIDE.md §6`) is already correct — plain, one sentence, no marketing voice.
