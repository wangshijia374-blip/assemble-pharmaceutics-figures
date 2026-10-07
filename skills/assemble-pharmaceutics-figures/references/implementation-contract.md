# Implementation contract

## Vector typography commands

`fonts-inspect` / `fonts-normalize` provide optional Illustrator-backed object inspection, final-width font assessment, and source-preserving AI/PDF derivatives. They are separate from automatic assembly: without `--run-illustrator`, scripts remain pending. Ambiguous roles and noneditable text remain review items. See [vector-typography.md](vector-typography.md) for sizing, role overrides, partial normalization, and visual verification requirements. Do not claim the whole figure is normalized merely because live text sizes passed.

Use this table before promising an output. A documented layout principle is not the same as an automated guarantee.

## Enforced by the CLI

- read-only source scanning and project-confined outputs;
- panel-level visible-content bounds with explicit approval;
- manifest approval invalidation after any declared manifest/panel/layout field, journal setting, caption fact, panel order, or top-level/nested child source file changes;
- A4 portrait (`210 × 297 mm`) working artboard by default;
- proportional placement of the full source behind an editable Illustrator clipping mask;
- bilingual placeholders for missing scientific facts;
- top-level source hashes, duplicate-source detection, editable layer routing, and Illustrator attempt status;
- `compact-journal-v1` defaults: uppercase 8 pt labels, -2/-1.5 mm label offsets, 1.8/4.5 mm hierarchical spacing, and A4 overflow rejection;
- top-level `panel.layout` validation (`row`, `column`, `column_span`, `row_span`, `group_id`, `align`) with deterministic effective-content placement shared by SVG and JSX;
- top-level `same_size_group` sizing on approved `effective_content` or approved normalized `plot_area`, with width/height target, actual, and residual QA measurements;
- `plot_area` is never guessed: members without approved normalized plot-area data are explicitly flagged in QA and are not claimed equal;
- compact QA output for configured vs measured gaps, SVG/JSX label-coordinate agreement, utilization, largest empty region, distortion, effective DPI, protected content, and construction paths.

## Review-only until implemented

The current engine does not automatically solve child content bounds, child-level `plot_area`, shared headers, treatment color identity, hard neighbor constraints beyond declared top-level spans, nested/composite achieved-size tolerances, final exported glyph bounding boxes, or final Illustrator/PDF physical measurement.

When any of these are required:

1. record them in the manifest/proposal;
2. create a separate review preview or custom JSX without overwriting an approved Figure;
3. show exact child-source mapping, effective bounds, target dimensions, and unresolved risks;
4. obtain new bounds and layout approval after every source, order, bounds, group, or target-size change;
5. do not run the generic `assemble` path as proof of those advanced constraints;
6. the agent must not claim journal compliance, equal plot areas, or child-level traceability until the exported AI/PDF has been measured and verified.

Independent source files take priority over a summary raster when the user confirms they represent the same child items. Keep the summary raster as a non-export review reference and record source-to-child traceability manually until child manifests are implemented.

## QA interpretation

`qa_report.md` is a screening report, not a publication certificate. It currently checks readable sources, panel-level bounds status/risks, bilingual placeholders, declared DPI, and duplicate hashes. Final review must still verify effective output DPI, text size, plot-area equality, scale bars, axes, legends, statistics, reading order, spacing hierarchy, aspect ratio, artboard size, and hidden construction paths.
