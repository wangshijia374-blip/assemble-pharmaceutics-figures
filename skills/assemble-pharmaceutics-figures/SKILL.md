---
name: assemble-pharmaceutics-figures
description: Use when arranging pharmaceutics or biomedical research images into journal multi-panel figures, planning a/b/c panel order, generating Adobe Illustrator layouts, or drafting bilingual figure legends from confirmed experimental facts.
---

# Assemble Pharmaceutics Figures

## Overview

Plan the scientific story before styling. Treat filenames and visual classification as suggestions; require the user to confirm panel meaning and order before Illustrator assembly.

## Core contract

Use four gates: **scan → explain → user approval → assemble**. Source pixels remain read-only. Scientific facts come only from the user-confirmed manifest. Layout is based on approved effective content, never merely the source canvas.

Before promising automation, read `references/implementation-contract.md`. It separates behavior enforced by the CLI from advanced layout rules that remain review-only. The agent must not present a review preview or a clean QA report as proof of final journal compliance.

## Quick start

From the project root, create an isolated environment and install the package with its test tools:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
```

Use the installed entry point (or `.\.venv\Scripts\pharmfig.exe` if the environment is not activated):

```powershell
pharmfig scan .\examples\synthetic-input --run-id Figure3
pharmfig propose .\runs\Figure3\manifest.yaml
```

Open `runs\Figure3\manifest.yaml`, then edit and confirm the panel labels/order, `content_guess`, placement reasons, `caption_facts.zh`, `caption_facts.en`, journal settings, and any optional `layer_override`. Keep unknown facts as placeholders. Review `runs\Figure3\proposal.md`, then run `pharmfig approve ...` yourself and type the literal `APPROVE` gate only after the manifest is correct. Finally run `pharmfig assemble ...`. All generated files stay in the manifest's project-local `output_folder`, normally `runs\Figure3`.

Before scientific approval, detect and review visible-content bounds:

```powershell
pharmfig bounds .\runs\Figure3\manifest.yaml
# Review content_bounds_review.png and adjust normalized bounds in the manifest.
pharmfig bounds-approve .\runs\Figure3\manifest.yaml
pharmfig approve .\runs\Figure3\manifest.yaml
```

Optional integrations are installed separately:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[windows]"  # Illustrator COM on Windows
.\.venv\Scripts\python.exe -m pip install -e ".[vision]"   # OpenAI cloud vision
```

## Required workflow

1. Run a read-only scan. Do not move, rename, overwrite, crop, or upload source images.
2. Generate `proposal.md` and show the user one core conclusion, exact `a/b/c/d` file mapping, placement reasons, narrative sequence, confidence, and unresolved facts.
3. Ask the user to confirm, reorder, replace, merge, or remove panels. Do not call `approve` on the user's behalf.
4. Run `bounds` and show `content_bounds_review.png`. Treat every red rectangle as a candidate, not a final crop.
5. Require the user to review every panel boundary. Preserve axes, ticks, legends, error bars, significance marks, scale bars, text, and internal spacing in composite panels. Adjust `content_bounds.normalized` when requested.
6. Run interactive `bounds-approve` only after per-panel review and require the literal `APPROVE_BOUNDS` gate. A general instruction such as “按内容大小排版” does not approve individual boundaries.
7. Run interactive `approve` after bounds approval and require the literal `APPROVE` gate.
8. Run `assemble`. Approval automatically becomes invalid if files, order, captions, journal settings, or content bounds changed.
9. For CLI-enforced layouts, return the editable AI/JSX, preview, bilingual captions, traceability table, and screening QA report. For review-only advanced layouts, return a separate preview and unresolved-constraint report; do not claim the generic AI/PDF satisfies those constraints.

## Commands

Prefer the installed `pharmfig` entry point. The relative wrapper `python scripts/pharmfig.py` is available when running from this skill directory and discovers its project root from its own location; `PHARMFIG_PROJECT_ROOT` is only an optional override.

```text
scan <image-folder> --run-id Figure3
propose <manifest.yaml> --journal <optional.yaml>
bounds <manifest.yaml>
bounds-approve <manifest.yaml>
approve <manifest.yaml>
assemble <manifest.yaml> --run-illustrator
caption <manifest.yaml> --bilingual
qa <manifest.yaml>
vision <manifest.yaml> --panels a,c
```

For `vision`, first inspect the exact resized previews and visible text/content. They have local filenames removed, but their pixels are not anonymized and no OCR redaction occurs. The CLI separately requires `REVIEWED_SAFE` and then the per-operation `UPLOAD` confirmation.

Never combine `scan`, `propose`, `bounds`, `bounds-approve`, `approve`, and `assemble` into an unreviewed operation.

## Visible-content sizing contract

- Never size a panel solely from the raster canvas dimensions when visible-content bounds are available.
- Remove only outer blank or transparent margins. Preserve the internal layout of a composite panel.
- Keep source pixels untouched. Illustrator must place the complete source and use an editable clipping mask for non-destructive display.
- Scale and center from the approved effective-content width and height; anchor the panel label to the approved content top-left.
- Default to `mode: manual`, `padding_percent: 2`, and `status: draft`.
- Automatic alpha or border-color detection is only a candidate. Low-contrast, complex-background, vector, or PDF panels require manual review.
- `assemble` must fail if any panel lacks approved content bounds, even if the scientific panel order was previously approved.

## Adaptive journal layout contract

- Use an `A4 portrait` artboard (`210 × 297 mm`) for every review layout, Illustrator document, PDF preview, and Figure run by default. Do not switch individual figures to landscape merely to reduce whitespace.
- Keep the A4 portrait artboard as the stable working canvas across a project. A named journal's final trim/export dimensions may override the export profile, but must not silently change the approved working orientation.
- Use a hierarchical spacing model: the `intra-group gap` between images belonging to one experimental group must be smaller than the `inter-group gap` between top-level panels. `compact-journal-v1` defaults to 1.8 mm and 4.5 mm and measures top-level gaps in QA; nested intra-group placement remains review-only.
- Keep repeated images or charts at comparable visible-content sizes. Match their effective heights or widths; never force identical raster canvases or distort aspect ratios.
- Put panels or child items of the same scientific or visual type in an explicit `same_size_group`. Compare the approved visible content for images and the approved `plot_area` for statistical plots; never use the source canvas as the equality basis.
- Record `size_basis`, `target_effective_width_mm`, and/or `target_effective_height_mm` for every `same_size_group`. Preserve aspect ratio. If both target dimensions cannot be met without distortion, use the dimension that controls scientific readability and report the residual mismatch in QA.
- For an existing raster composite, keep its internal combination unchanged. If child plotting areas cannot be reviewed reliably, match only the composite's approved effective-content dimension and flag that child-level equality remains unresolved.
- Before treating a raster composite as indivisible, scan for its independent source files. When confirmed independent sources exist, use them as child items, preserve the approved scientific grouping/order, and retain source-to-child traceability; do not use the summary raster merely because it was found first.
- Do not rearrange the internal grid of an existing composite panel unless the user explicitly approves that internal change. Resize and reposition the composite as one unit.
- For a newly constructed composite, record its internal grid in the manifest, including row counts, item order, intra-row gap, inter-row gap, and centering rule.
- Optimize in this order: preserve scientific reading order and requested spatial relations; protect labels, axes, legends, scale bars, and statistics; equalize repeated visual units; reduce unused whitespace; then balance the page.
- A requested relation such as `B → D → E` is a hard spatial constraint. Do not sacrifice it merely to obtain a symmetric grid.
- The target journal profile overrides generic A4 presentation. If no journal is named, generate a review layout and separately report the closest common single-column, double-column, and full-page export sizes.

The CLI enforces top-level explicit semantic spans, approved effective-content sizing, `same_size_group`, and compact QA measurements through `compact-journal-v1`. Read `references/compact-journal-layout.md` before declaring `layout`, `same_size_group`, or `size_basis`. Child-level constraints and unapproved `plot_area` remain review risks; obtain a fresh approval before any custom Illustrator run.

## Scientific integrity contract

Before final layout approval, inspect and, when needed, normalize editable vector text at its final placed size. Read `references/vector-typography.md`: `fonts-inspect` distinguishes live vector text from raster/outlined/linked content; `fonts-normalize` creates a separate derivative using reviewed body/title/panel roles. Preserve relative superscripts and scientific content, render the derivative, and reassess bounds before switching sources. Generated JSX is pending work, not proof of inspection or normalization.

- Do not infer treatment groups, sample size, statistics, scale bars, molecular identity, or mechanism from appearance.
- Keep unknown caption facts as `[待确认]` and `[TO CONFIRM]`.
- Keep representative images adjacent to their matching quantification.
- Prefer evidence order: design → formulation → representative result → quantification → function → in vivo → distribution/histology → omics → pathway → validation.
- If panels do not support one conclusion, recommend multiple figures instead of forcing a visually balanced collage.
- Never make pixel edits, selective exclusions, blot crops, or statistical changes.

Read `references/privacy-and-integrity.md` before cloud vision. Read `references/journal-layout.md` when configuring dimensions. Read `references/caption-contract.md` before finalizing legends.

For Western blot multi-panel figures, read `references/wb-layout-reference.md`. Learn its normalized spacing and alignment ratios; do not copy the source artboard dimensions or scientific labels.

For mixed pharmaceutics figures containing schemes, characterization, microscopy matrices, dose-response plots, heatmaps, or in-vivo panels, read `references/adaptive-article-layout.md` before proposing panel spans.
