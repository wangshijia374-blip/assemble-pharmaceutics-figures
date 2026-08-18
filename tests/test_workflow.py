from pathlib import Path

import pytest
import yaml
from PIL import Image, ImageDraw

from pharmfig.workflow import (
    ApprovalError,
    PharmFigError,
    PrivacyError,
    analyze_cloud_panels,
    approve_manifest,
    assemble_manifest,
    approve_content_bounds,
    build_captions,
    detect_content_bounds,
    load_manifest,
    prepare_cloud_thumbnails,
    propose_manifest,
    run_qa,
    scan_folder,
)
from pharmfig.cli import main as cli_main
from pharmfig import workflow


def make_image(path: Path, size=(120, 80), color="white") -> None:
    Image.new("RGB", size, color).save(path)


def make_content_image(path: Path) -> None:
    image = Image.new("RGB", (200, 100), "white")
    ImageDraw.Draw(image).rectangle((40, 20, 159, 79), fill="black")
    image.save(path)


def approve_bounds_then_figure(manifest_path: Path) -> None:
    detect_content_bounds(manifest_path)
    approve_content_bounds(manifest_path)
    approve_manifest(manifest_path)


def test_scan_adds_draft_manual_content_bounds(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_content_image(source / "panel.png")

    manifest = load_manifest(scan_folder(source, run, "demo"))
    bounds = manifest["panels"][0]["content_bounds"]

    assert bounds["mode"] == "manual"
    assert bounds["status"] == "draft"
    assert bounds["padding_percent"] == 2


def test_skill_requires_hierarchical_spacing_and_preserves_composites():
    skill = (Path(__file__).parents[1] / "skills" / "assemble-pharmaceutics-figures" / "SKILL.md").read_text(encoding="utf-8")
    reference = (Path(__file__).parents[1] / "skills" / "assemble-pharmaceutics-figures" / "references" / "journal-layout.md").read_text(encoding="utf-8")
    assert "intra-group gap" in skill
    assert "inter-group gap" in skill
    assert "Do not rearrange the internal grid of an existing composite panel" in skill
    assert "intra_gap_mm" in reference
    assert "inter_gap_mm" in reference


def test_skill_defaults_all_review_artboards_to_a4_portrait():
    skill = (Path(__file__).parents[1] / "skills" / "assemble-pharmaceutics-figures" / "SKILL.md").read_text(encoding="utf-8")
    reference = (Path(__file__).parents[1] / "skills" / "assemble-pharmaceutics-figures" / "references" / "journal-layout.md").read_text(encoding="utf-8")
    assert "A4 portrait" in skill
    assert "210 × 297 mm" in skill
    assert "artboard_width_mm: 210" in reference
    assert "artboard_height_mm: 297" in reference


def test_skill_links_wb_reference_layout_profile():
    root = Path(__file__).parents[1] / "skills" / "assemble-pharmaceutics-figures"
    skill = (root / "SKILL.md").read_text(encoding="utf-8")
    profile = root / "references" / "wb-layout-reference.md"
    assert "references/wb-layout-reference.md" in skill
    assert profile.is_file()
    text = profile.read_text(encoding="utf-8")
    assert "170 × 200 mm" in text
    assert "A4 portrait" in text
    assert "intra-strip" in text


def test_skill_links_adaptive_article_layout_profile():
    root = Path(__file__).parents[1] / "skills" / "assemble-pharmaceutics-figures"
    skill = (root / "SKILL.md").read_text(encoding="utf-8")
    profile = root / "references" / "adaptive-article-layout.md"
    assert "references/adaptive-article-layout.md" in skill
    assert profile.is_file()
    text = profile.read_text(encoding="utf-8").lower()
    assert "semantic span" in text
    assert "shared row and column headers" in text
    assert "inset" in text
    assert "color identity" in text
    assert "semantic grouping" in text


def test_bounds_detect_outer_whitespace_and_write_review(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_content_image(source / "panel.png")
    manifest_path = scan_folder(source, run, "demo")

    outputs = detect_content_bounds(manifest_path)
    manifest = load_manifest(manifest_path)
    bounds = manifest["panels"][0]["content_bounds"]

    assert bounds["detection_basis"] == "border_color"
    assert bounds["normalized"] == pytest.approx([0.188, 0.18, 0.812, 0.82], abs=0.015)
    assert bounds["status"] == "draft"
    assert outputs["review_png"].exists()
    assert outputs["review_md"].exists()


def test_assemble_requires_approved_content_bounds(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_content_image(source / "panel.png")
    manifest_path = scan_folder(source, run, "demo")
    approve_manifest(manifest_path)

    with pytest.raises(ApprovalError, match="content bounds"):
        assemble_manifest(manifest_path)


def test_content_bounds_change_revokes_figure_approval(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_content_image(source / "panel.png")
    manifest_path = scan_folder(source, run, "demo")
    approve_bounds_then_figure(manifest_path)
    manifest = load_manifest(manifest_path)
    manifest["panels"][0]["content_bounds"]["normalized"][0] += 0.01
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")

    with pytest.raises(ApprovalError):
        assemble_manifest(manifest_path)


def test_generated_jsx_uses_content_bounds_and_editable_clipping_mask(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_content_image(source / "panel.png")
    manifest_path = scan_folder(source, run, "demo")
    approve_bounds_then_figure(manifest_path)

    jsx = assemble_manifest(manifest_path)["jsx"].read_text(encoding="utf-8-sig")

    assert "groupItems.add()" in jsx
    assert "group.clipped = true" in jsx
    assert "effectiveW" in jsx
    assert "effectiveH" in jsx
    assert "clip.clipping = true" in jsx


def test_traceability_records_approved_content_bounds(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_content_image(source / "panel.png")
    manifest_path = scan_folder(source, run, "demo")
    approve_bounds_then_figure(manifest_path)

    traceability = assemble_manifest(manifest_path)["traceability"].read_text(encoding="utf-8-sig")

    assert "content_bounds" in traceability
    assert "approved" in traceability


def test_qa_reports_unapproved_content_bounds(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_content_image(source / "panel.png")
    manifest_path = scan_folder(source, run, "demo")

    qa = run_qa(manifest_path).read_text(encoding="utf-8")

    assert "内容边界尚未逐面板批准" in qa


def test_bounds_cli_requires_literal_confirmation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_content_image(source / "panel.png")
    manifest_path = scan_folder(source, run, "demo")
    assert cli_main(["bounds", str(manifest_path)]) == 0
    monkeypatch.setattr("builtins.input", lambda _: "NO")
    assert cli_main(["bounds-approve", str(manifest_path)]) == 2
    assert load_manifest(manifest_path)["panels"][0]["content_bounds"]["status"] == "draft"


def test_scan_creates_draft_without_touching_source(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    image = source / "uptake.png"
    make_image(image)
    before = image.stat().st_mtime_ns

    manifest_path = scan_folder(source, run, "demo")
    manifest = load_manifest(manifest_path)

    assert manifest["approval"]["status"] == "draft"
    assert manifest["panels"][0]["source"] == str(image.resolve())
    assert image.stat().st_mtime_ns == before
    assert not list(source.glob("*.jsx"))


def test_propose_explains_panel_order_and_uses_unknown_placeholders(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_image(source / "uptake.png")
    make_image(source / "IMG0032.png")

    manifest_path = scan_folder(source, run, "demo")
    proposal_path = propose_manifest(manifest_path)
    text = proposal_path.read_text(encoding="utf-8")
    manifest = load_manifest(manifest_path)

    assert "建议面板顺序" in text
    assert "放置理由" in text
    assert manifest["panels"][1]["content_guess"] == "待确认"
    assert "[待确认]" in manifest["panels"][1]["caption_facts"]["zh"]


def test_assemble_rejects_unapproved_and_changed_manifests(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_image(source / "a.png")
    manifest_path = scan_folder(source, run, "demo")

    with pytest.raises(ApprovalError):
        assemble_manifest(manifest_path)

    approve_manifest(manifest_path)
    manifest = load_manifest(manifest_path)
    manifest["panels"][0]["label"] = "b"
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")

    with pytest.raises(ApprovalError):
        assemble_manifest(manifest_path)


def test_approved_assembly_outputs_jsx_traceability_and_captions(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_image(source / "pca.png", size=(160, 80))
    manifest_path = scan_folder(source, run, "demo")
    propose_manifest(manifest_path)
    detect_content_bounds(manifest_path)
    approve_content_bounds(manifest_path)
    approve_manifest(manifest_path)

    outputs = assemble_manifest(manifest_path, run_illustrator=False)
    captions = build_captions(manifest_path, bilingual=True)

    assert outputs["jsx"].exists()
    assert outputs["traceability"].exists()
    assert outputs["qa"].exists()
    assert captions["zh"].exists()
    assert captions["en"].exists()
    assert "[TO CONFIRM]" in captions["en"].read_text(encoding="utf-8")
    assert "[待确认]" in captions["zh"].read_text(encoding="utf-8")


def test_source_change_revokes_approval(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    image = source / "panel.png"
    make_image(image)
    manifest_path = scan_folder(source, run, "demo")
    approve_manifest(manifest_path)
    make_image(image, color="black")

    with pytest.raises(ApprovalError):
        assemble_manifest(manifest_path)


def test_cloud_thumbnails_require_per_panel_authorization_and_explicit_confirmation(tmp_path: Path):
    source = tmp_path / "secret-research-name"
    run = tmp_path / "run"
    source.mkdir()
    make_image(source / "unpublished-target.png")
    manifest_path = scan_folder(source, run, "demo")

    with pytest.raises(PrivacyError):
        prepare_cloud_thumbnails(manifest_path, ["a"], confirm_upload=True, confirm_content_safe=True)

    manifest = load_manifest(manifest_path)
    manifest["panels"][0]["label"] = "a"
    manifest["panels"][0]["cloud_vision_authorized"] = True
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")

    with pytest.raises(PrivacyError):
        prepare_cloud_thumbnails(manifest_path, ["a"], confirm_upload=False, confirm_content_safe=True)

    with pytest.raises(PrivacyError, match="visible text/content"):
        prepare_cloud_thumbnails(manifest_path, ["a"], confirm_upload=True)

    thumbnails = prepare_cloud_thumbnails(
        manifest_path,
        ["a"],
        confirm_upload=True,
        confirm_content_safe=True,
    )
    assert thumbnails[0].name == "panel-001.jpg"
    assert "unpublished-target" not in str(thumbnails[0])


def test_generated_jsx_has_editable_layers_and_proportional_resize(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_image(source / "panel.png")
    manifest_path = scan_folder(source, run, "demo")
    propose_manifest(manifest_path)
    detect_content_bounds(manifest_path)
    approve_content_bounds(manifest_path)
    approve_manifest(manifest_path)

    jsx = assemble_manifest(manifest_path)["jsx"].read_text(encoding="utf-8-sig")

    assert "01_PANEL_LABELS" in jsx
    assert "04_MICROSCOPY" in jsx
    assert "Math.min(maxW / effectiveW, maxH / effectiveH)" in jsx
    assert "PDFSaveOptions" in jsx


def test_generated_jsx_resizes_before_centering_item_in_panel_box(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_image(source / "panel.png")
    manifest_path = scan_folder(source, run, "demo")
    propose_manifest(manifest_path)
    detect_content_bounds(manifest_path)
    approve_content_bounds(manifest_path)
    approve_manifest(manifest_path)

    jsx = assemble_manifest(manifest_path)["jsx"].read_text(encoding="utf-8-sig")

    resize_at = jsx.index("item.resize(scale, scale);")
    position_at = jsx.index("item.position =")
    assert resize_at < position_at
    assert "(maxW - effectiveW) / 2" in jsx
    assert "(maxH - effectiveH) / 2" in jsx


def test_cloud_analysis_uses_only_resized_filename_free_previews_and_revokes_approval(tmp_path: Path):
    source = tmp_path / "secret-project-name"
    run = tmp_path / "run"
    source.mkdir()
    make_image(source / "secret-target.png")
    manifest_path = scan_folder(source, run, "demo")
    propose_manifest(manifest_path)
    manifest = load_manifest(manifest_path)
    manifest["panels"][0]["cloud_vision_authorized"] = True
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    approve_manifest(manifest_path)
    captured = {}

    def fake_transport(images, prompt):
        captured["images"] = images
        captured["prompt"] = prompt
        return [{"label": "a", "content_guess": "统计图（需用户确认）", "confidence": "中"}]

    analyze_cloud_panels(
        manifest_path,
        ["a"],
        confirm_upload=True,
        confirm_content_safe=True,
        transport=fake_transport,
    )
    updated = load_manifest(manifest_path)

    assert all("secret-target" not in str(path) for path in captured["images"])
    assert "secret-project-name" not in captured["prompt"]
    assert "anonym" not in captured["prompt"].lower()
    assert "visible text" in captured["prompt"].lower()
    assert updated["approval"]["status"] == "draft"
    assert updated["panels"][0]["caption_facts"]["en"] == "[TO CONFIRM]"


@pytest.mark.parametrize("run_id", ["../escape", r"..\escape", r"C:\escape", "/absolute"])
def test_scan_rejects_absolute_and_traversal_run_ids(tmp_path: Path, run_id: str):
    source = tmp_path / "source"
    source.mkdir()
    make_image(source / "panel.png")

    with pytest.raises(PharmFigError, match="run ID"):
        scan_folder(source, tmp_path / "run", run_id)


def test_cli_rejects_traversal_run_id_before_creating_output(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    make_image(source / "panel.png")

    assert cli_main(["scan", str(source), "--run-id", "../outside-run"]) == 2
    assert not (workflow.PROJECT_ROOT / "outside-run").exists()


@pytest.mark.parametrize("operation", ["propose", "caption", "qa", "cloud", "assemble"])
def test_manifest_output_folder_is_validated_before_every_write(tmp_path: Path, operation: str):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_image(source / "panel.png")
    manifest_path = scan_folder(source, run, "demo")
    propose_manifest(manifest_path)
    manifest = load_manifest(manifest_path)
    manifest["panels"][0]["cloud_vision_authorized"] = True
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    approve_manifest(manifest_path)
    outside = workflow.PROJECT_ROOT.parent / "pharmfig-outside-test"
    manifest = load_manifest(manifest_path)
    manifest["output_folder"] = str(outside)
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")

    with pytest.raises(PharmFigError, match="outside project root"):
        if operation == "propose":
            propose_manifest(manifest_path)
        elif operation == "caption":
            build_captions(manifest_path)
        elif operation == "qa":
            run_qa(manifest_path)
        elif operation == "cloud":
            prepare_cloud_thumbnails(
                manifest_path,
                ["a"],
                confirm_upload=True,
                confirm_content_safe=True,
            )
        else:
            assemble_manifest(manifest_path)
    assert not outside.exists()


def test_layout_preview_embeds_raster_and_uses_vector_placeholder_without_paths(tmp_path: Path):
    source = tmp_path / "private-source-name"
    run = tmp_path / "run"
    source.mkdir()
    make_image(source / "patient-visible-name.png", color="red")
    (source / "confidential-vector.pdf").write_bytes(b"%PDF-1.4\n")
    manifest_path = scan_folder(source, run, "demo")
    propose_manifest(manifest_path)
    detect_content_bounds(manifest_path)
    approve_content_bounds(manifest_path)
    approve_manifest(manifest_path)

    preview = assemble_manifest(manifest_path)["preview"].read_text(encoding="utf-8")

    assert "data:image/png;base64," in preview
    assert "Preview unavailable for .pdf" in preview
    assert str(source) not in preview
    assert "patient-visible-name" not in preview
    assert "confidential-vector" not in preview


def test_generated_jsx_routes_panels_to_semantic_layers_and_honors_override(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    for name in ["scheme.png", "histology.png", "plot.png", "unknown.png", "override.png"]:
        make_image(source / name)
    manifest_path = scan_folder(source, run, "demo")
    manifest = load_manifest(manifest_path)
    guesses = {
        "scheme.png": "schematic workflow",
        "histology.png": "representative image / histology",
        "plot.png": "statistical plot",
        "unknown.png": "unclassified content",
        "override.png": "unclassified content",
    }
    for index, panel in enumerate(manifest["panels"]):
        panel["label"] = chr(ord("a") + index)
        panel["content_guess"] = guesses[panel["relative_source"]]
        if panel["relative_source"] == "override.png":
            panel["layer_override"] = "04_MICROSCOPY"
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    detect_content_bounds(manifest_path)
    approve_content_bounds(manifest_path)
    approve_manifest(manifest_path)

    jsx = assemble_manifest(manifest_path)["jsx"].read_text(encoding="utf-8-sig")

    expected = {
        "scheme.png": "05_SCHEMATICS",
        "histology.png": "04_MICROSCOPY",
        "plot.png": "03_STATISTICAL_PLOTS",
        "unknown.png": "07_NOTES_NONEXPORT",
        "override.png": "04_MICROSCOPY",
    }
    for filename, layer in expected.items():
        assert f"layers['{layer}'].groupItems.add();" in jsx
        matching_line = next(line for line in jsx.splitlines() if filename in line)
        assert f"layers['{layer}']" in matching_line


def test_qa_flags_missing_chinese_english_and_bilingual_incompleteness(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_image(source / "one.png")
    make_image(source / "two.png")
    manifest_path = scan_folder(source, run, "demo")
    manifest = load_manifest(manifest_path)
    manifest["panels"][0]["label"] = "a"
    manifest["panels"][0]["caption_facts"] = {"zh": "已确认事实", "en": "[TO CONFIRM]"}
    manifest["panels"][1]["label"] = "b"
    manifest["panels"][1]["caption_facts"] = {"zh": "", "en": "Confirmed fact"}
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")

    report = run_qa(manifest_path).read_text(encoding="utf-8")

    assert "[a] English caption facts are missing" in report
    assert "[b] Chinese caption facts are missing" in report
    assert "[a] Bilingual caption facts are incomplete" in report
    assert "[b] Bilingual caption facts are incomplete" in report


@pytest.mark.parametrize("illustrator_success", [False, True])
def test_illustrator_attempt_archives_stale_outputs_and_writes_precise_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    illustrator_success: bool,
):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_image(source / "panel.png")
    manifest_path = scan_folder(source, run, "demo")
    propose_manifest(manifest_path)
    detect_content_bounds(manifest_path)
    approve_content_bounds(manifest_path)
    approve_manifest(manifest_path)
    stale_ai = run / "demo.ai"
    stale_pdf = run / "demo.pdf"
    stale_ai.write_bytes(b"old-ai")
    stale_pdf.write_bytes(b"old-pdf")

    def fake_run(jsx: Path):
        if illustrator_success:
            jsx.with_suffix(".ai").write_bytes(b"new-ai")
            jsx.with_suffix(".pdf").write_bytes(b"new-pdf")
        return illustrator_success, "completed" if illustrator_success else "failed deliberately"

    monkeypatch.setattr(workflow, "_run_illustrator", fake_run)
    outputs = assemble_manifest(manifest_path, run_illustrator=True)
    status = outputs["status"].read_text(encoding="utf-8")
    archives = list((run / "revisions").glob("*/demo.ai"))

    assert len(archives) == 1
    assert archives[0].read_bytes() == b"old-ai"
    assert next((run / "revisions").glob("*/demo.pdf")).read_bytes() == b"old-pdf"
    assert f"success={str(illustrator_success).lower()}" in status
    assert "attempted=true" in status
    assert "manifest_hash=" in status
    assert "timestamp=" in status
    if illustrator_success:
        assert stale_ai.read_bytes() == b"new-ai"
        assert stale_pdf.read_bytes() == b"new-pdf"
    else:
        assert not stale_ai.exists()
        assert not stale_pdf.exists()


def test_non_ascii_source_and_run_id_survive_jsx_generation(tmp_path: Path):
    source = tmp_path / "来源目录"
    run = tmp_path / "运行输出"
    source.mkdir()
    image = source / "显微 图像.png"
    make_image(image)
    manifest_path = scan_folder(source, run, "图三")
    propose_manifest(manifest_path)
    detect_content_bounds(manifest_path)
    approve_content_bounds(manifest_path)
    approve_manifest(manifest_path)

    jsx_path = assemble_manifest(manifest_path)["jsx"]
    jsx = jsx_path.read_text(encoding="utf-8-sig")

    assert jsx_path.name == "图三.jsx"
    assert "显微 图像.png" in jsx
    assert "来源目录" in jsx


def test_adaptive_layout_defines_same_attribute_effective_content_size_contract():
    skill_root = Path(__file__).parents[1] / "skills" / "assemble-pharmaceutics-figures"
    skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    profile = (skill_root / "references" / "adaptive-article-layout.md").read_text(encoding="utf-8")

    assert "same_size_group" in skill
    assert "same_size_group" in profile
    assert "size_basis" in profile
    assert "plot_area" in profile
    assert "target_effective_width_mm" in profile
    assert "target_effective_height_mm" in profile
    assert "same scientific or visual type" in profile
    assert "source canvas" in profile


def test_adaptive_layout_prefers_independent_sources_over_raster_composite():
    skill_root = Path(__file__).parents[1] / "skills" / "assemble-pharmaceutics-figures"
    skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    profile = (skill_root / "references" / "adaptive-article-layout.md").read_text(encoding="utf-8")

    assert "independent source files" in skill
    assert "independent source files" in profile
    assert "summary raster" in profile
    assert "traceability" in profile


def test_scan_defaults_to_real_a4_portrait_artboard(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_image(source / "panel.png")

    manifest = load_manifest(scan_folder(source, run, "a4-demo"))

    assert manifest["journal"]["artboard_width_mm"] == 210
    assert manifest["journal"]["artboard_height_mm"] == 297
    assert manifest["journal"]["orientation"] == "portrait"
    assert manifest["journal"]["intra_gap_mm"] < manifest["journal"]["inter_gap_mm"]


def test_layout_metadata_change_revokes_approval(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_image(source / "panel.png")
    manifest_path = scan_folder(source, run, "layout-hash-demo")
    propose_manifest(manifest_path)
    detect_content_bounds(manifest_path)
    approve_content_bounds(manifest_path)
    approve_manifest(manifest_path)
    manifest = load_manifest(manifest_path)
    manifest["panels"][0]["same_size_group"] = "bar-chart-pair"
    manifest["panels"][0]["size_basis"] = "plot_area"
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")

    with pytest.raises(ApprovalError, match="revoked"):
        assemble_manifest(manifest_path)


def test_skill_distinguishes_enforced_and_review_only_capabilities():
    root = Path(__file__).parents[1] / "skills" / "assemble-pharmaceutics-figures"
    skill = (root / "SKILL.md").read_text(encoding="utf-8")
    contract = (root / "references" / "implementation-contract.md").read_text(encoding="utf-8")

    assert "implementation-contract.md" in skill
    assert "Enforced by the CLI" in contract
    assert "Review-only until implemented" in contract
    assert "same_size_group" in contract
    assert "child content bounds" in contract
    assert "must not claim" in contract


def test_nested_child_source_change_revokes_approval(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_image(source / "parent.png")
    make_image(source / "child.png", color="red")
    manifest_path = scan_folder(source, run, "child-hash-demo")
    manifest = load_manifest(manifest_path)
    manifest["panels"] = [panel for panel in manifest["panels"] if panel["relative_source"] == "parent.png"]
    manifest["panels"][0]["label"] = "a"
    manifest["panels"][0]["children"] = [{"id": "a1", "source": str((source / "child.png").resolve())}]
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    detect_content_bounds(manifest_path)
    approve_content_bounds(manifest_path)
    approve_manifest(manifest_path)

    make_image(source / "child.png", color="blue")

    with pytest.raises(ApprovalError, match="revoked"):
        assemble_manifest(manifest_path)


def test_root_layout_metadata_change_revokes_approval(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_image(source / "panel.png")
    manifest_path = scan_folder(source, run, "root-layout-hash-demo")
    propose_manifest(manifest_path)
    detect_content_bounds(manifest_path)
    approve_content_bounds(manifest_path)
    manifest = load_manifest(manifest_path)
    manifest["layout_constraints"] = {"reading_order": ["a"]}
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    approve_manifest(manifest_path)
    manifest = load_manifest(manifest_path)
    manifest["layout_constraints"]["reading_order"] = ["b", "a"]
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")

    with pytest.raises(ApprovalError, match="revoked"):
        assemble_manifest(manifest_path)
