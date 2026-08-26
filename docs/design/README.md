# Design — "Examinations Office"

The visual system for the teacher-facing UI (`assembly`, `bank`, and the login page),
plus the design canvas that documents it.

Written 2026-08-25.

## Where the design actually lives

**`static/css/paper.css` is the system.** It is loaded by `templates/base.html` and it is
the single source of truth — the design canvas in this folder is built from that same
file, so the pictures and the running app cannot drift apart.

| File | Loaded by |
|---|---|
| `static/css/paper.css` | `base.html` — every screen |
| `static/css/paper-print.css` | `assembly/print.html` — the printed paper |
| `static/css/paper-gate.css` | `registration/login.html` — the sign-in page |

There is no build step for the app. Edit the CSS, reload the page.

## The direction, in one paragraph

The screens borrow their language from printed examination stationery, because that is
what this tool makes. Warm paper stock (`--paper`, hue 84), blue-black ink (`--ink`,
hue 258), hairline rules instead of boxes, and one marker's red (`--stamp`) that appears
only where a marker would use it, with a tick-green (`--seal`) for things already
approved. Three typefaces do three jobs: **Libre Caslon Text** for titles, prose and the
exam paper itself; **Archivo** for labels, navigation and buttons; **IBM Plex Mono** for
counts, codes and references. All three come from Google Fonts with real fallbacks.

Four rules hold the whole thing together, and breaking any one of them is what makes an
interface look machine-generated:

- **no cards** — content sits on one sheet of paper, divided by rules
- **no corner radii** — squares everywhere; the only circle is an OMR bubble
- **no shadows** — depth comes from rule weight (2px, 1px, hairline, dotted)
- **no gradients** — flat ink, with a faint SVG paper grain behind everything

The one move worth protecting: **the unit picker is an OMR answer sheet.** The checkbox
itself is styled into the bubble (`appearance: none`), the whole row is the label, and
`:has(input:checked)` tints the row. Units with no approved bank are struck through, not
merely dimmed.

## The design canvas

`examinations-office.html` is a published Claude Design canvas showing all five screens
plus a reference sheet. It is a **picture of the design, not the app** — editing an
artboard changes the picture only.

Rebuild it after changing `static/css/paper.css`:

```bash
node docs/design/build.mjs
```

That regenerates the six `.dc.html` artboards from `parts/<Name>.body.html` + the shared
stylesheet. `canvas.json` holds the layout, the two pages and the sticky notes; frame
heights live in both `build.mjs` (`SIZES`) and `canvas.json` and must agree, or artboard
content gets clipped.

To preview an artboard in a plain browser without publishing:

```bash
node docs/design/preview.mjs Main
```

Re-seed and republish with the `/design` skill's `seed-canvas.mjs`; the artboard content
is real data read out of `db.sqlite3`, not placeholder text, so it will go stale if the
bank changes a lot.

## Two small view changes the design needed

- `assembly/views.py` — `_units_with_counts` now `select_related("grammar_point")`, so
  the unit rows can show the grammar focus without one query per unit.
- `bank/views.py` — the coverage view now also passes `approved_total`, `pending_total`
  and `type_peak` (the largest per-type count, used to scale the coverage bars and to
  avoid dividing by zero on an empty bank).
