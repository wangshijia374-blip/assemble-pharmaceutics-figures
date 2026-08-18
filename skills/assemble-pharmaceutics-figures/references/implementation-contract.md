# Implementation contract

Use this table before promising an output. A documented layout principle is not the same as an automated guarantee.

## Enforced by the CLI

- read-only source scanning and project-confined outputs;
- panel-level visible-content bounds with explicit approval;
- manifest approval invalidation after any declared manifest/panel/layout field, journal setting, caption fact, panel order, or top-level/nested child source file changes;
- A4 portrait (`210 × 297 mm`) working artboard by default;
- proportional placement of the full source behind an editable Illustrator clipping mask;
- bilingual placeholders for missing scientific facts;
- top-level source hashes, duplicate-source detection, editable layer routing, and Illustrator attempt status.

## Review-only until implemented

The current generic layout engine does not automatically solve semantic spans, hard neighbor constraints, child content bounds, child `plot_area`, `same_size_group` targets, shared headers, treatment color identity, or achieved-size tolerances.

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
