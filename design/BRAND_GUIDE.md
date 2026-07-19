# LegoLog Brand Guide

## 0. Context: what we looked at

Before defining LegoLog's brand, we scanned how the LEGO ecosystem presents itself across three tiers:

| Tier | Sites | Visual pattern |
|---|---|---|
| **Official** | LEGO.com | Bold red/yellow, rounded "brick geometry" shapes, the new **Typewell** custom typeface (co-designed with Colophon Foundry) that borrows curves and spacing from brick studs. High-gloss product photography, big rounded corners, lots of white space, playful and retail-first. |
| **Cataloging / marketplace** | BrickLink, Rebrickable, Brickset | Dense, utilitarian, spreadsheet-adjacent. Small type, heavy tables, minimal color (mostly blue links + neutral chrome). Built for power users who want data density over delight — closer to phpBB/Bootstrap defaults than a modern product. |
| **Fan media** | The Brothers Brick, BrickFanatics, BrickNerd | Editorial/blog layouts, red or yellow accent on a white or dark card grid, big set photography as the hero, magazine-style hierarchy. |
| **Investor/portfolio tools** | BrickEconomy, Bricqer | Dashboard-first: dark or light "SaaS" chrome, data tables, sparkline charts, sidebar nav — visually closer to a fintech product than a toy site. |

**Where LegoLog sits:** LegoLog is not a retailer, not a marketplace, and not a news site — it's a personal utility (closer to the BrickEconomy/Bricqer tier) that answers one question fast: *"what can I build from what I already own?"* The brand should feel like a well-made **tool**, not a toy-store storefront: calm, dense-but-legible, fast to scan. It should nod at LEGO's playfulness (color, the stud motif) without imitating LEGO's official trade dress (Typewell font, exact red/yellow lockup, brick photography) — both because that trade dress is proprietary, and because a cataloging tool has different jobs-to-be-done than a retail site.

Sources: [BrickNerd — LEGO's New Visual Brand Identity](https://bricknerd.com/home/a-close-look-at-legos-new-visual-brand-identity-4-17-24), [LEGO Brand Colors](https://pickcoloronline.com/brands/lego/), [BrandColorCode — LEGO](https://www.brandcolorcode.com/lego)

## 1. Brand personality

- **Builder's tool, not a toy shop.** Utilitarian confidence — like Linear, GitHub, or Vercel — applied to a LEGO hobbyist's workflow.
- **Quietly playful.** One motif (the 2×2 stud mark) carries all the "fun," so the UI around it can stay calm and legible.
- **Fast and honest.** Numbers, percentages, and part counts are the product. Never obscure them behind decoration.

**Personality is / is not**

| Is | Is not |
|---|---|
| Calm, dark, focused | Loud, retail, gradient-heavy |
| Data-dense but legible | Cluttered or cramped |
| One confident accent color | A rainbow of brand colors used equally |
| Subtly brick-flavored | A LEGO.com clone or trade-dress lookalike |

## 2. Logo / mark

Keep the existing **2×2 stud grid** mark (`red / yellow / blue / green`, one stud per quadrant) — it's the strongest brand asset already in the codebase (`public/index.html`, header). It:

- reads instantly as "LEGO" via color + shape alone, no wordmark dependency
- uses the four classic brick colors as a palette *reference* rather than copying LEGO's logo lockup
- scales down to favicon size better than a wordmark would

**Wordmark:** `Lego` in the UI's neutral text color + `Log` in brand yellow (`LegoLog`, single word, capital L twice) — already implemented, keep it. Don't add a tagline to the lockup; it competes with the mark at small sizes.

**Clear space & minimum size:** keep at least 1 stud-width of clear space around the mark; don't render the stud grid below 16px (favicon floor) or the individual studs stop reading as circles.

**Missing today:** there's no favicon, no `apple-touch-icon`, no social/OG image, and no `manifest.json`. The stud mark should be exported as a static SVG/PNG and wired up (see Website Audit, §Branding gaps).

## 3. Color

### 3.1 Brand accent colors (the "brick four")

Sourced from the classic LEGO brick palette (not the LEGO wordmark's exact red, since that's used at a different intensity for a different purpose):

| Token | Hex | Use |
|---|---|---|
| `brand-yellow` (primary) | `#FACC15` | Primary actions, active states, brand accent — the one color allowed to dominate |
| `brand-red` | `#EF4444` | Destructive actions, "missing/short" data, errors |
| `brand-blue` | `#3B82F6` | Informational accents, links, secondary highlight |
| `brand-green` | `#22C55E` | Success, "fully buildable," positive states |

Rule: **only one accent color should be visually dominant on a screen at a time** (currently yellow, for primary actions). The other three are reserved for semantic meaning (status), not decoration — don't use red/blue/green as arbitrary UI chrome.

### 3.2 Neutral scale (the "workbench")

Dark, low-chroma slate neutrals — already close to correct in the current build (Tailwind's `slate` scale). This is the 90% of the UI's surface area, so it needs to stay boring on purpose:

| Token | Approx. | Use |
|---|---|---|
| `bg` | `slate-950 #020617` | App background |
| `surface` | `slate-900 #0F172A` | Cards, header, panels |
| `surface-raised` | `slate-800 #1E293B` | Inputs, hover states, chips |
| `border` | `slate-800 / slate-700` | Dividers, card borders |
| `text-primary` | `slate-200 #E2E8F0` | Body text |
| `text-muted` | `slate-400 #94A3B8` | Metadata, secondary text |
| `text-disabled` | `slate-500 #64748B` | Placeholders — **do not** use for anything that must be read; fails contrast at small sizes (see Usability Audit) |

### 3.3 Contrast rule

Every text/background pairing must clear **WCAG AA (4.5:1 for body text, 3:1 for large/bold text)**. `text-slate-500` on `bg-slate-950`/`bg-slate-900` currently fails this at the sizes it's used — flagged in the audit, fixed in the design system tokens (`text-muted` is remapped to `slate-400`).

## 4. Typography

- **Body/UI face:** system sans stack (`-apple-system, "Segoe UI", Inter, Roboto, sans-serif`) — free, fast (no webfont request), and already what the app ships. Keep it; it reads as "tool," not "toy."
- **Display face (new):** a rounded geometric sans for the wordmark and section headers only — e.g. **Baloo 2** or **Fredoka**, both free (Google Fonts), both echo LEGO's rounded brick-geometry letterforms (a nod to Typewell's soft terminals) without using LEGO's proprietary font.
  - Load it for the `<h1>` wordmark and empty-state headlines only; everything else (labels, data, buttons, body copy) stays on the system sans stack for performance and legibility at small sizes.
- **Scale:** 12 / 13 / 14 / 16 / 20 / 24px — matches what's already in use (Tailwind `text-xs` → `text-xl`); no need to introduce a larger scale, this is a dense utility app, not a marketing page.
- **Numerals:** tabular/monospaced figures for stat counters (`stats`, part counts, coverage %) so numbers don't jiggle the layout as they update — currently proportional, worth switching (`font-variant-numeric: tabular-nums`).

## 5. Iconography & motifs

- **Stud motif:** the 2×2 stud grid is the one recurring brand shape. Reuse it sparingly — header logo, favicon, loading spinner (four studs pulsing in sequence), empty states. Don't scatter studs across every card; it dilutes the mark.
- **Icons:** keep to a single inline icon set (the app currently mixes literal Unicode glyphs `✓ ✕ −` with none from a shared set). Standardize on one lightweight icon set (e.g. Lucide/Feather — MIT licensed, tree-shakeable, no build step needed via CDN) for consistency and accessibility (`aria-label`s instead of bare glyphs).
- **Color swatches:** for LEGO part colors, keep the small rounded-square chip pattern already used in the missing-parts table — it's the correct pattern (matches BrickLink/Rebrickable convention for part-color display) and should be reused everywhere a part color is shown (search results currently omit it).
- **Photography:** none needed. All imagery is user-generated (Rebrickable set photos on white backgrounds) — the brand shouldn't introduce its own photography style, just a consistent frame (white rounded card, `object-contain`, fixed aspect ratio) for that third-party imagery, which the current build already does correctly.

## 6. Voice

- Short, declarative, numbers-first: *"✓ Buildable"*, *"missing 42 of 210"*, *"3 sets · 1,204 parts."*
- No exclamation points, no retail enthusiasm ("Amazing deals!"). This is a spreadsheet with better typography, and the copy should read that way.
- Empty/zero states get one sentence of plain instruction, not marketing copy (existing copy — *"No sets yet. Search above to add the sets you own"* — is the right tone; keep future empty states consistent with it).

## 7. What to keep vs. change from the current build

| Keep | Change |
|---|---|
| Dark slate neutral base | `text-slate-500` used for readable copy → contrast fails AA |
| Stud-grid logo mark | No favicon/OG image exported from it |
| Yellow as single dominant accent | Red/green/blue used inconsistently as both semantic *and* decorative color |
| System-sans body text | No display face for headline moments — brand currently has no typographic personality beyond color |
| Rounded-square part-color chips | Unicode glyphs (`✓ ✕ −`) instead of a real icon set with `aria-label`s |
