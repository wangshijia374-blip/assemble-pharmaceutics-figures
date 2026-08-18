# Generic biomedical layout profile

Use this only as a starting point; target-journal instructions override it.

| Setting | Default |
|---|---|
| Working artboard | A4 portrait |
| `artboard_width_mm` | 210 |
| `artboard_height_mm` | 297 |
| Single column | 89 mm |
| Double column | 180 mm |
| Typeface | Arial or compatible sans serif |
| Minimum final text | 7 pt |
| Raster preview | 300 dpi minimum |
| Panel labels | lowercase `a.` by default |
| `intra_gap_mm` | 2 mm |
| `inter_gap_mm` | 4 mm |
| Outer margin | 4 mm |

Default working-canvas configuration:

```yaml
artboard_width_mm: 210
artboard_height_mm: 297
orientation: portrait
```

Preserve aspect ratio and place a representative image beside its quantification. Supported label styles are `A`, `a.`, `a,`, and `(a)`.

## Visible-content sizing

Panel scale is based on the approved visible-content rectangle, not the full raster canvas. Use a 2% safety padding by default, preserve composite-panel internal spacing, and retain the full source as an editable placed item behind an Illustrator clipping mask. Every candidate boundary requires per-panel approval before assembly.

## Adaptive packing

Treat spacing as hierarchical rather than uniform:

- `intra_gap_mm` separates repeated images/charts inside one top-level panel.
- `inter_gap_mm` separates A/B/C-level panels and must be larger than `intra_gap_mm`.
- Scale both values proportionally when the target print width changes; keep the ratio between 1.5 and 2.5 unless a journal template specifies otherwise.
- Equalize repeated elements by approved visible-content bounds, not by source-canvas width or height.
- Preserve an existing composite panel as one unit. Internal reflow requires a new proposal and approval.
- Use content-aware packing to minimize unused whitespace, but never enlarge a low-information panel solely to fill a rectangular hole.

Journal profiles change. Always load and cite the named journal's current official author/figure guide before final export; do not treat these generic defaults as submission requirements.
