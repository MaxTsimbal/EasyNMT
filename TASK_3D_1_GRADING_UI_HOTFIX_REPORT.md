# Task 3D.1 — Grading Clarity & Compact Quiz UI

## Fixed grading behavior

The old rubric parser split only on new lines and semicolons. Answers such as `1) studies 2) was taking 3) visited` were treated as one long segment, causing valid second and third parts to receive zero points.

The new parser accepts:

- three separate lines;
- `1) ... 2) ... 3) ...` on one line;
- semicolon-separated answers;
- pipe-separated answers;
- exactly three comma-separated answers.

Every part remains positional and independently graded. Article-only differences (`a`, `an`, `the`) do not remove a point, but spelling, auxiliary, verb-form, and content mistakes remain visible.

## New review output

Each three-point task now returns a numbered breakdown:

- `✅` for accepted parts;
- `❌` for incorrect or missing parts;
- a short reason;
- the correct form for that exact part.

## UI changes

- smaller sticky progress card;
- smaller 1–12 navigation buttons;
- compact score-band legend;
- smaller bottom submit panel;
- bottom panel remains sticky;
- multiline review feedback renders correctly;
- mobile submit bar stays compact and does not expand into a large block.

## Verification

- Python compile check: passed.
- Full automated suite: **145 tests passed**.
- Added production regressions matching the screenshots: passed.
