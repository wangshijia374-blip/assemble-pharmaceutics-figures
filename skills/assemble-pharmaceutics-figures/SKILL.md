---
name: assemble-pharmaceutics-figures
description: Use when arranging pharmaceutics or biomedical research images into journal multi-panel figures, planning a/b/c panel order, generating Adobe Illustrator layouts, or drafting bilingual figure legends from confirmed experimental facts.
---

# Assemble Pharmaceutics Figures

## Overview

Plan the scientific story before styling. Treat filenames and visual classification as suggestions; require the user to confirm panel meaning and order before Illustrator assembly.

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
9. Return the editable AI/JSX, preview, bilingual captions, traceability table, and QA report.

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

## Scientific integrity contract

- Do not infer treatment groups, sample size, statistics, scale bars, molecular identity, or mechanism from appearance.
- Keep unknown caption facts as `[待确认]` and `[TO CONFIRM]`.
- Keep representative images adjacent to their matching quantification.
- Prefer evidence order: design → formulation → representative result → quantification → function → in vivo → distribution/histology → omics → pathway → validation.
- If panels do not support one conclusion, recommend multiple figures instead of forcing a visually balanced collage.
- Never make pixel edits, selective exclusions, blot crops, or statistical changes.

Read `references/privacy-and-integrity.md` before cloud vision. Read `references/journal-layout.md` when configuring dimensions. Read `references/caption-contract.md` before finalizing legends.
