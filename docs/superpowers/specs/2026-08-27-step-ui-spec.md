# STEP Platform — UI Design Contract

Written 2026-08-27. Binding on every STEP screen. Supersedes the visual language of
the first implementation, which was rejected as generic.

**Why this document exists.** The first STEP interface was built to the client mockups'
skeleton and styled ad-hoc. The result was a navy-sidebar, white-content, blue-accent,
four-stat-card dashboard with 10px radii and soft shadows — the single most reproduced
layout in software. Character asserted in CSS comments does not survive generic bones.
This contract fixes the bones before any CSS is written.

---

## 1. The direction: Dossier & Stamp

The true subject of this system is **a wet rubber stamp on a sheet of paper**. A teacher
fills a report, a director signs and stamps it by hand, the teacher photographs the stamp,
and an administrator files it. That is a paper process with a database bolted on — so the
interface is official stationery, not a dashboard.

This also makes STEP a sibling of the existing **Examinations Office** system
(`static/css/paper.css`) rather than its opposite, which removes the two-visual-languages
problem recorded in the spine spec §7.3. STEP is the same institution's other department:
same paper stock, different letterhead.

**What this direction forbids, absolutely:**

| Forbidden | Because |
|---|---|
| Cards, panels with borders on all four sides | Content sits on one sheet, divided by rules |
| Any `border-radius` above `0` | Official forms have square corners |
| Any `box-shadow` | Depth comes from rule weight, not elevation |
| Any gradient | Flat ink only |
| Blue as an accent | It is the tell |
| Icons inside coloured squares or circles | The single strongest generated-UI signal |
| A navy sidebar against white content | See above |
| Four equal stat cards in a row | Replaced by the record strip, §5.2 |
| A separate top application bar | Replaced by the letterhead, §5.1 |

---

## 2. Colour

No dashboard blue anywhere. The palette is paper, ink, the two colours a marker uses, and a
set of stationery inks.

```css
/* Paper — light and clean. An earlier pass ran muddy and the whole page read as drab. */
--paper:      #F4EFE3;
--paper-deep: #EBE4D4;  /* the folder tab: nav rail */
--surface:    #FCFAF4;  /* raised sheets: docket, record strip, rows on hover */
--wash:       #F8F4EA;

--ink:        #171310;  /* headings, rules */
--ink-body:   #302822;  /* body copy */
--ink-soft:   #554B41;
--pencil:     #857868;  /* annotations, hints, metadata */
--rule:       #DDD3C0;  /* hairlines */
--rule-firm:  #B5A992;  /* structural rules */

--stamp:      #A62F1C;  /* stamp red — late, returned, required */
--seal:       #2C6B4C;  /* green ink — accepted, complete */
```

`--stamp` and `--seal` appear **only** where a marker would use them, and carry status and
nothing else.

**Stationery inks.** Six hues so the register has life. Every one is plausible in a pen or a
stamp pad; none is a dashboard blue.

```css
--ink-violet: #5F4B8B;  /* carbon-copy purple */
--ink-teal:   #1F6A6E;
--ink-ochre:  #8E6A18;
--ink-umber:  #8A5330;
--ink-plum:   #6E3B57;
```

**Colour sits on the category, never on the status.** Each obligation section gets one ink,
applied to its category label. Status keeps `--stamp` / `--seal` / ink alone. Because the two
never share a hue, they can never be confused — which is what makes it safe to have colour
at all.

---

## 3. Typography

Three faces, three jobs, all with full Cyrillic — school, district and director names will
arrive in it.

```css
--font-text: "Literata", Georgia, serif;          /* headings, prose, the paper itself */
--font-ui:   "Commissioner", "Segoe UI", sans-serif; /* labels, nav, buttons */
--font-mono: "PT Mono", ui-monospace, monospace;  /* figures, dates, references */
```

Literata was drawn for long-form reading, so it stays comfortable at the sizes this
interface uses and is simply better looking than the state workhorses it replaced.
Commissioner is humanist and legible at the small sizes labels live at. PT Mono stays
because figures on a form should look typed.

**Rules:**

- Every **figure, date and reference** is `--font-mono` with `tabular-nums`.
- **Uppercase is reserved for small labels only** — the `.label` idiom, and the equivalents
  on nav headings, field labels, buttons and status marks. Nothing at reading size is ever
  uppercase. Uppercase letterspacing at volume is what made the first pass read as harsh.
- Body copy and headings are `--font-text`. Page title 42px at weight 400 — large and
  light, not heavy; a form's heading is authoritative because of its rule, not its weight.
- No font weight below 400.

---

## 3a. Space

The first pass was cramped, which is most of what made it ugly. Minimums:

| | |
|---|---|
| Body | 17px / 1.62 |
| Sheet padding | 38px 44px 96px |
| Between blocks | 44px |
| Register row | 19px vertical |
| Record cell | 20px 22px |
| Column gap | 56px |

---

## 4. Structure

**Rules replace boxes.** Four weights, and nothing else carries structure:

```
2px solid --ink        section boundary, letterhead
1px solid --rule-firm  block boundary
1px solid --rule       row divider
1px dotted --rule      soft grouping
```

**Proportions are deliberately not the defaults.** Nav rail is `236px`. There is no top
application bar at all.

**The grain.** A single low-opacity SVG noise layer over the page ground. It must be
subtle enough that removing it is only noticeable side by side.

---

## 5. Required components

### 5.1 Letterhead (replaces the top application bar)

The top of the sheet carries a letterhead, not an app chrome bar: programme name at left,
the teacher's name, school and a file reference at right, bounded above and below by a 2px
ink rule. This single change is what stops the interface reading as an app.

The file reference is real, not decoration: `STEP/{region code}/{educator id}`.

### 5.2 Record strip (replaces the four stat cards)

One bounded strip divided by vertical hairlines into four cells. Figures in `--font-mono`
at 30px, labels in `--font-ui` caps beneath. No icons. No individual borders. No shadows.
It reads as the boxes at the head of a form, because that is what it is.

### 5.3 The docket (the "do this next" block)

The one unmissable element (spine spec §7.1). A block bounded top and bottom by 2px ink
rules, carrying:

- an **`ACTION REQUIRED` stamp impression**, rotated `-3deg`, in `--stamp`;
- the obligation set in `--font-text` at 33px, weight 400;
- the deadline in plain words — *"4 days late"*, never a date to subtract;
- one square, ink-filled button.

### 5.4 Stamp impression — the signature device

A rotated, double-ruled outline box with letterspaced caps inside, in `--stamp` or
`--seal`. Used for `ACTION REQUIRED`, `ACCEPTED`, `RETURNED`. **At most one impression per
screen region**, and never more than two per screen. Overused, it becomes decoration and
the whole thing collapses into pastiche.

Rotation is the memorable detail. It must look pressed by a human hand, so the angle is
never `0`, and never the same twice on one screen.

### 5.5 Status marks

Status is always a **word**, per the accessibility rule carried over from the previous
system. Colour and treatment reinforce it:

| State | Treatment |
|---|---|
| Late | `--stamp`, caps, bold, with a struck rule through it |
| Due today | `--stamp`, caps, bold |
| Due soon | `--ink`, caps, dotted underline |
| Scheduled | `--pencil`, caps |
| With reviewer | `--ink-soft`, caps, dotted underline |
| Accepted | `--seal`, caps, with a tick |
| Needs correction | `--stamp`, caps, bold |

---

## 6. Motion

One moment only: on load, the docket's stamp **presses in** — `scale(1.06) → 1` with
opacity, over 260ms, once. Everything else is instant.

Everything is disabled under `prefers-reduced-motion`.

---

## 7. Carried over, unchanged

These survive from the previous contract and remain binding:

- **Status is a word**, never colour alone.
- **Model vocabulary never reaches a user** — no `not_started`, no `evidence_spec`.
- **Deadlines are relative first**, absolute second.
- **Errors are instructions**, in the same words as the button.
- **Self-reported director data is labelled** wherever it appears (spine spec §5.10).
- **The phone is a first-class case** — the stamped report is photographed on one.
- **One thing per page**; one primary action per screen.

---

## 8. Acceptance

The redesign is done when all of the following hold, checked against the running app:

1. `grep -c "border-radius" static/css/step.css` returns only `0`-valued declarations.
2. No `box-shadow` and no `linear-gradient` in the stylesheet.
3. No dashboard-blue token exists. The carbon-copy violet `#5F4B8B` is blue-dominant by a
   naive channel test and is permitted; a naive scan will flag it, so check the hue, not the
   channel.
4. The computed body font-family resolves to Literata, labels to Commissioner, figures to
   PT Mono.
5. No element with all four borders that contains other content (no cards).
6. The nav rail computes to 236px; there is no element functioning as a top app bar.
7. At most two stamp impressions render on any single screen.
8. The phone layout produces no horizontal overflow at 375px.
9. Every status in the DOM carries a word, not only a colour class.
10. The full test suite still passes.
