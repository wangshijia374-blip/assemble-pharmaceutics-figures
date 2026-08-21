# Compact journal layout profile

`compact-journal-v1` is the CLI-enforced A4 portrait working profile for compact research multi-panel figures. It distills reusable journal-page geometry only; it does not copy scientific claims, panel content, treatment labels, or coordinates from any reference paper.

## Defaults

- A4 portrait: `210 × 297 mm` with a 4 mm safety margin.
- Uppercase bold panel labels (`label_style: A`), 8 pt.
- Label anchor: approved effective-content top-left, `x=-2 mm`, `y=-1.5 mm`.
- Hierarchical spacing: `intra_gap_mm: 1.8`; `inter_gap_mm: 4.5`.

## Manifest layout fields

```yaml
layout:
  row: 0
  column: 0
  column_span: 2
  row_span: 1
  group_id: response-plots
  align: effective-top-left # effective-top-left | effective-top | effective-left | start | center | end
same_size_group: response-plots
size_basis: effective_content # or plot_area
target_effective_width_mm: 32
```

The engine preserves manifest order, retains approved effective-content aspect ratios, rejects overlapping spans and A4 overflow, and uses the same calculated content rectangles for SVG preview and JSX.

`effective_content` equality is enforced only for approved top-level content bounds. `plot_area` equality requires an explicitly approved `plot_area.normalized` mapping inside each member's approved content bounds; otherwise QA records an unresolved risk and the engine does not infer plot geometry. Declare width, height, or both targets. When both targets conflict with a member's aspect ratio, `size_control_dimension: width|height` selects the controlling dimension and QA reports the residual without stretching pixels.

## Measurement gates

QA distinguishes configured from measured content-edge gaps, reports SVG/JSX shared-label coordinate error, groups same-size measurements by `same_size_group`, and finds the largest empty axis-aligned region. Verify labels within 0.5 mm, gaps within 0.3 mm, comparable-image size within 2%, and approved plot areas within 3% after Illustrator/PDF measurement.
