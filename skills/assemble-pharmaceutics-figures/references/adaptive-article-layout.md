# Adaptive journal-article layout profile

Use this profile for mixed pharmaceutics and biomedical figures. It distills reusable layout patterns from a published multi-figure article without copying its scientific content, treatment labels, conclusions, or exact coordinates.

## Evidence-led structure

Prefer this narrative when the available evidence supports it:

1. preparation or experimental scheme;
2. physicochemical characterization;
3. representative phenomenon plus matching quantification;
4. dose response or functional validation;
5. mechanism or multivariate summary;
6. in-vivo efficacy, distribution, histology, and safety.

This sequence is a proposal, not a factual claim. Keep the user-confirmed scientific order as the hard constraint.

## Semantic span, not equal cells

Assign each panel a span from its effective aspect ratio, information density, and role:

- A horizontal scheme may span one, two, or all columns. Do not force every scheme to 100% width.
- A representative micrograph should remain large enough for morphology and scale-bar inspection.
- Closely related size/zeta or image/quantification panels should be adjacent and may form one composite block.
- A heatmap, long time series, or dense legend receives more area than a simple two-bar comparison.
- Repeated panels use comparable visible-content dimensions even when their source canvases differ.

Pack in confirmed reading order. Penalize unused whitespace, inconsistent repeated-panel scale, broken image-quantification adjacency, and violations of requested spatial relationships. Never reduce those penalties by stretching an image.

## Repeated-image matrices

- Use shared row and column headers once per matrix instead of repeating full labels in every cell.
- Keep every matrix cell at the same effective image size and align scale bars consistently.
- Start with 1.5–2 mm between cells, 2–3 mm from cells to shared headers, 3–4 mm between panels in one evidence group, and 6–8 mm between different evidence groups.
- Treatment-by-time, tissue-by-treatment, and histology matrices should read left-to-right then top-to-bottom.

## Insets and callouts

- Use an inset only when it reveals a feature that is genuinely unreadable at the main scale.
- Draw a restrained rectangle around the source region and connect it to the inset with thin, non-crossing keylines.
- Preserve both overview and inset scale bars when they represent different magnifications.
- An inset remains part of its parent panel and does not receive a new top-level letter.

## Cross-panel visual grammar

- Keep treatment color identity stable across all charts in one Figure. Do not recolor a group merely to balance a panel.
- Match plotting-area height, axis type size, stroke weight, error-bar style, and legend order across comparable charts.
- Place uppercase or lowercase panel labels according to the selected journal profile, at a consistent offset from the effective-content top-left.
- Put scale bars inside image panels with consistent contrast and location where the image permits.

## Comparable-content sizing

Items of the same scientific or visual type must use the same actual-content size, not merely the same source canvas or outer file dimensions. Declare the comparison in the manifest:

```yaml
same_size_group: bar-chart-pair
size_basis: plot_area
target_effective_width_mm: 30
target_effective_height_mm: 24
```

- Statistical graphs and spectra use the approved axis `plot_area`; microscopy uses the approved image area; repeated diagrams use approved visible-content bounds.
- Apply the group at child-item level when comparable plots live inside composite panels. Keep titles, legends, tick labels, significance marks, and error bars visible, but do not let their unequal outer margins define the plot size.
- Preserve aspect ratio. When exact width and height equality conflict, prioritize the dimension that controls readability, record the achieved dimensions, and report the remaining percentage mismatch in QA.
- Do not put unrelated content types in one `same_size_group` merely to make a symmetric page.
- Existing raster composites remain intact. If child `plot_area` bounds cannot be reviewed reliably, match the approved composite effective-content dimension and mark child-level equality as unresolved instead of cropping, stretching, or rebuilding the composite.
- First check whether the apparent composite has confirmed independent source files. If it does, assemble those sources as child items, keep their approved order and group membership, and record complete traceability. Exclude the old summary raster from placement to prevent duplicate evidence; retain it only as a non-export review reference.

## Semantic grouping

- Use whitespace first to communicate groups.
- Use a thin or dashed outline only when it marks a real semantic grouping such as one animal cohort, one longitudinal series, or one shared experimental block.
- Do not draw decorative boxes around unrelated panels, and keep construction paths hidden from final export.

## Adaptive proposal contract

Before assembly, report for every panel:

1. semantic role and confirmed scientific relationship;
2. approved effective-content bounds and aspect ratio;
3. proposed row, column, and span;
4. neighbors that must remain adjacent;
5. repeated-size group, shared-header group, and color-identity group;
6. unresolved risks such as unreadable labels, low resolution, missing scale bars, or excess internal whitespace.

If the first packing leaves large holes, change spans and row grouping before increasing gaps. If legibility still fails, recommend splitting the Figure rather than shrinking every panel.
