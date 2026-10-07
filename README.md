# assemble-pharmaceutics-figures

Approval-gated local tooling and a Codex Skill for arranging pharmaceutics and biomedical research images into editable Adobe Illustrator figures.

## Safety defaults

- Source images remain read-only and local.
- Panel order requires explicit scientific approval.
- Visible-content bounds require per-panel review before assembly.
- Illustrator places complete source files and uses editable clipping masks; it does not overwrite source pixels.
- Missing caption facts remain `[待确认]` / `[TO CONFIRM]`.
- Run artifacts and research images under `runs/` are excluded from Git.

## Install

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
```

Optional integrations:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[windows]" # Illustrator COM
.\.venv\Scripts\python.exe -m pip install -e ".[vision]"  # Optional cloud vision
```

## Workflow

```powershell
pharmfig scan <image-folder> --run-id Figure1
pharmfig propose .\runs\Figure1\manifest.yaml
pharmfig bounds .\runs\Figure1\manifest.yaml
# Review content_bounds_review.png and edit normalized bounds if needed.
pharmfig bounds-approve .\runs\Figure1\manifest.yaml
pharmfig approve .\runs\Figure1\manifest.yaml
pharmfig assemble .\runs\Figure1\manifest.yaml --run-illustrator
```

`bounds-approve` requires `APPROVE_BOUNDS`; scientific approval separately requires `APPROVE`. Changing sources, panel order, caption facts, journal settings, or content bounds invalidates approval.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The reusable Skill is in `skills/assemble-pharmaceutics-figures/`.

中文完整说明见 [`SKILLS.md`](SKILLS.md)。
# Vector font inspection and normalization

Use `pharmfig fonts-inspect source.svg --output runs/font-check --final-width-mm 80 --run-illustrator` to inspect actual Illustrator objects. Then run `pharmfig fonts-normalize runs/font-check/font-audit.json --output runs/font-copy --final-width-mm 80 --roles roles.json --run-illustrator` to create a separate AI/PDF copy when needed. Default final sizes are body 8 pt, title 10 pt, panel labels 12 pt; ambiguous roles require review. Raster and outlined text are not rewritten. Source files remain untouched.

See [the typography workflow](skills/assemble-pharmaceutics-figures/references/vector-typography.md), including final-size scaling, mixed-content limits, and PDF rendering checks. Install `.[windows]` for Illustrator automation and `.[vector]` for single-page PDF validation. The repository includes a synthetic [SVG example](examples/typography-demo.svg); no research data is needed for testing.
