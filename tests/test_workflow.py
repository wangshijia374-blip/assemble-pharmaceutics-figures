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
        "unknown.png": "08_UNCLASSIFIED_CONTENT",
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


def test_scan_defaults_to_compact_journal_v1_manifest(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_image(source / "panel.png")

    manifest = load_manifest(scan_folder(source, run, "compact-defaults"))
    journal = manifest["journal"]

    assert journal["compactness_profile"] == "compact-journal-v1"
    assert journal["label_style"] == "A"
    assert journal["label_font_pt"] == 8
    assert journal["label_offset_x_mm"] == -2
    assert journal["label_offset_y_mm"] == -1.5
    assert journal["intra_gap_mm"] == 1.8
    assert journal["inter_gap_mm"] == 4.5


def test_explicit_layout_spans_use_effective_content_and_preserve_manifest_order(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_content_image(source / "wide.png")
    make_content_image(source / "square.png")
    make_content_image(source / "tall.png")
    manifest_path = scan_folder(source, run, "explicit-layout")
    manifest = load_manifest(manifest_path)
    for index, panel in enumerate(manifest["panels"]):
        panel["label"] = chr(ord("a") + index)
    manifest["panels"][0]["layout"] = {"row": 0, "column": 0, "column_span": 2, "row_span": 1, "group_id": "top", "align": "start"}
    manifest["panels"][1]["layout"] = {"row": 1, "column": 0, "column_span": 1, "row_span": 1, "group_id": "bottom", "align": "center"}
    manifest["panels"][2]["layout"] = {"row": 1, "column": 1, "column_span": 1, "row_span": 1, "group_id": "bottom", "align": "end"}
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    approve_bounds_then_figure(manifest_path)

    boxes, _ = workflow._layout(load_manifest(manifest_path))

    assert [box["label"] for box in boxes] == ["a", "b", "c"]
    assert boxes[0]["w"] > boxes[1]["w"] + boxes[2]["w"] - 0.4
    assert boxes[1]["y"] == pytest.approx(boxes[2]["y"], abs=0.3)
    assert boxes[0]["content_h"] == pytest.approx(boxes[0]["content_w"] / 2, abs=0.05)


def test_invalid_explicit_layout_is_rejected_before_assembly(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_image(source / "panel.png")
    manifest_path = scan_folder(source, run, "invalid-layout")
    manifest = load_manifest(manifest_path)
    manifest["panels"][0]["layout"] = {"row": 0, "column": 0, "column_span": 0}
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    approve_bounds_then_figure(manifest_path)

    with pytest.raises(PharmFigError, match="column_span"):
        assemble_manifest(manifest_path)


def test_same_size_group_matches_approved_effective_content_width(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_content_image(source / "first.png")
    make_content_image(source / "second.png")
    manifest_path = scan_folder(source, run, "same-size")
    manifest = load_manifest(manifest_path)
    for index, panel in enumerate(manifest["panels"]):
        panel["label"] = chr(ord("a") + index)
        panel["same_size_group"] = "plots"
        panel["size_basis"] = "effective_content"
        panel["target_effective_width_mm"] = 32
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    approve_bounds_then_figure(manifest_path)

    boxes, _ = workflow._layout(load_manifest(manifest_path))

    assert [box["content_w"] for box in boxes] == pytest.approx([32, 32], abs=0.05)
    assert max(box["same_size_residual_percent"] for box in boxes) <= 2


def test_plot_area_without_approved_bounds_is_reported_as_layout_risk(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_image(source / "plot.png")
    manifest_path = scan_folder(source, run, "plot-area-risk")
    manifest = load_manifest(manifest_path)
    panel = manifest["panels"][0]
    panel["label"] = "a"
    panel["same_size_group"] = "plots"
    panel["size_basis"] = "plot_area"
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")

    qa = run_qa(manifest_path).read_text(encoding="utf-8")

    assert "plot_area" in qa
    assert "未批准" in qa


def test_svg_and_jsx_share_content_layout_and_uppercase_bold_offset_labels(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_content_image(source / "panel.png")
    manifest_path = scan_folder(source, run, "shared-layout")
    propose_manifest(manifest_path)
    approve_bounds_then_figure(manifest_path)

    outputs = assemble_manifest(manifest_path)
    jsx = outputs["jsx"].read_text(encoding="utf-8-sig")
    svg = outputs["preview"].read_text(encoding="utf-8")

    assert "var contentLeft" in jsx
    assert "label.position = [contentLeft + -2 * MM, contentTop + 1.5 * MM]" in jsx
    assert "characterAttributes.size = 8" in jsx
    assert 'font-weight="bold">A</text>' in svg
    assert 'x="' in svg and 'y="' in svg
    assert "preserveAspectRatio=\"xMidYMid meet\"" in svg


def test_qa_reports_compact_layout_measurements_and_protection_risks(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_content_image(source / "one.png")
    make_content_image(source / "two.png")
    manifest_path = scan_folder(source, run, "compact-qa")
    manifest = load_manifest(manifest_path)
    for index, panel in enumerate(manifest["panels"]):
        panel["label"] = chr(ord("a") + index)
        panel["same_size_group"] = "images"
        panel["size_basis"] = "effective_content"
        panel["target_effective_width_mm"] = 28
        panel["content_bounds"]["unresolved_risks"] = ["scale bar requires review"]
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    approve_bounds_then_figure(manifest_path)

    qa = run_qa(manifest_path).read_text(encoding="utf-8")

    for heading in ("标签偏移", "实际gap", "same-size", "画板利用率", "连续空白", "变形", "低有效DPI", "保护内容", "构造路径风险"):
        assert heading in qa


def test_skill_documents_compact_layout_as_enforced_capability():
    root = Path(__file__).parents[1] / "skills" / "assemble-pharmaceutics-figures"
    compact = root / "references" / "compact-journal-layout.md"
    skill = (root / "SKILL.md").read_text(encoding="utf-8")
    journal = (root / "references" / "journal-layout.md").read_text(encoding="utf-8")
    adaptive = (root / "references" / "adaptive-article-layout.md").read_text(encoding="utf-8")
    contract = (root / "references" / "implementation-contract.md").read_text(encoding="utf-8")

    assert compact.is_file()
    assert "compact-journal-v1" in compact.read_text(encoding="utf-8")
    assert "compact-journal-layout.md" in skill
    assert "compact-journal-v1" in journal
    assert "compact-journal-v1" in adaptive
    enforced = contract.split("## Review-only until implemented")[0]
    assert "same_size_group" in enforced
    assert "plot_area" in enforced


def test_qa_reports_measured_gap_values_from_the_shared_layout(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_content_image(source / "one.png")
    make_content_image(source / "two.png")
    manifest_path = scan_folder(source, run, "measured-gap")
    manifest = load_manifest(manifest_path)
    for index, panel in enumerate(manifest["panels"]):
        panel["label"] = chr(ord("a") + index)
        panel["layout"] = {"row": 0, "column": index, "group_id": "pair"}
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    approve_bounds_then_figure(manifest_path)

    qa = run_qa(manifest_path).read_text(encoding="utf-8")

    assert "水平实测" in qa
    assert "1.80 mm" in qa


def test_invalid_size_basis_is_rejected_even_before_same_size_grouping(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_image(source / "panel.png")
    manifest_path = scan_folder(source, run, "invalid-size-basis")
    manifest = load_manifest(manifest_path)
    manifest["panels"][0]["size_basis"] = "canvas"
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    approve_bounds_then_figure(manifest_path)

    with pytest.raises(PharmFigError, match="size_basis"):
        assemble_manifest(manifest_path)


def test_same_group_actual_content_gap_is_compact_not_the_unused_slot_gap(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_content_image(source / "one.png")
    make_content_image(source / "two.png")
    manifest_path = scan_folder(source, run, "content-gap")
    manifest = load_manifest(manifest_path)
    for index, panel in enumerate(manifest["panels"]):
        panel.update(label=chr(ord("a") + index), same_size_group="pair", size_basis="effective_content", target_effective_width_mm=30)
        panel["layout"] = {"row": 0, "column": index, "group_id": "pair", "align": "effective-top-left"}
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    approve_bounds_then_figure(manifest_path)

    boxes, _ = workflow._layout(load_manifest(manifest_path))

    assert boxes[1]["x"] - (boxes[0]["x"] + boxes[0]["w"]) == pytest.approx(1.8, abs=0.3)


def test_approved_plot_area_controls_outer_scale_and_same_size_measurements(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_image(source / "wide.png", size=(200, 100))
    make_image(source / "tall.png", size=(100, 200))
    manifest_path = scan_folder(source, run, "plot-area")
    manifest = load_manifest(manifest_path)
    plot_areas = ([0.25, 0.0, 0.75, 1.0], [0.0, 0.25, 1.0, 0.75])
    for index, (panel, area) in enumerate(zip(manifest["panels"], plot_areas)):
        panel.update(label=chr(ord("a") + index), same_size_group="plots", size_basis="plot_area", target_effective_width_mm=30)
        panel["plot_area"] = {"normalized": area, "status": "approved"}
        panel["layout"] = {"row": 0, "column": index, "group_id": "plots", "align": "effective-top-left"}
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    approve_bounds_then_figure(manifest_path)

    boxes, _ = workflow._layout(load_manifest(manifest_path))

    assert [box["basis_w"] for box in boxes] == pytest.approx([30, 30], abs=0.05)
    assert boxes[0]["w"] == pytest.approx(60, abs=0.1)
    assert boxes[1]["w"] == pytest.approx(30, abs=0.1)
    assert max(box["same_size_residual_percent"] for box in boxes) <= 3


def test_same_size_height_target_reports_unavoidable_width_residual_without_distortion(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_image(source / "square.png", size=(100, 100))
    make_image(source / "wide.png", size=(200, 100))
    manifest_path = scan_folder(source, run, "height-target")
    manifest = load_manifest(manifest_path)
    for index, panel in enumerate(manifest["panels"]):
        panel.update(label=chr(ord("a") + index), same_size_group="mixed", size_basis="effective_content", target_effective_height_mm=20)
        panel["layout"] = {"row": 0, "column": index, "group_id": "mixed", "align": "effective-top-left"}
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    approve_bounds_then_figure(manifest_path)

    boxes, _ = workflow._layout(load_manifest(manifest_path))

    assert [box["basis_h"] for box in boxes] == pytest.approx([20, 20], abs=0.05)
    assert boxes[1]["basis_w"] == pytest.approx(40, abs=0.05)
    assert all(box["same_size_height_residual_percent"] <= 0.01 for box in boxes)


def test_effective_top_left_and_row_span_use_real_content_edges(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_image(source / "tall.png", size=(100, 200))
    make_image(source / "top.png", size=(200, 100))
    make_image(source / "bottom.png", size=(200, 100))
    manifest_path = scan_folder(source, run, "top-left-span")
    manifest = load_manifest(manifest_path)
    layouts = ((0, 0, 1, 2), (0, 1, 1, 1), (1, 1, 1, 1))
    for index, (panel, (row, column, col_span, row_span)) in enumerate(zip(manifest["panels"], layouts)):
        panel["label"] = chr(ord("a") + index)
        panel["layout"] = {"row": row, "column": column, "column_span": col_span, "row_span": row_span, "group_id": "matrix", "align": "effective-top-left"}
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    approve_bounds_then_figure(manifest_path)

    boxes, _ = workflow._layout(load_manifest(manifest_path))

    assert boxes[0]["y"] == pytest.approx(boxes[1]["y"], abs=0.01)
    assert boxes[1]["x"] == pytest.approx(boxes[2]["x"], abs=0.01)
    assert boxes[2]["y"] - (boxes[1]["y"] + boxes[1]["h"]) == pytest.approx(1.8, abs=0.3)


def test_mixed_groups_sharing_a_column_boundary_reject_unsatisfiable_left_alignment(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    for name in ("top-a.png", "top-b.png", "bottom-a.png", "bottom-b.png"):
        make_content_image(source / name)
    manifest_path = scan_folder(source, run, "mixed-boundary")
    manifest = load_manifest(manifest_path)
    group_ids = ("top", "top", "bottom-left", "bottom-right")
    for index, (panel, group_id) in enumerate(zip(manifest["panels"], group_ids)):
        panel["label"] = chr(ord("a") + index)
        panel["same_size_group"] = "all"
        panel["size_basis"] = "effective_content"
        panel["target_effective_width_mm"] = 30
        panel["layout"] = {"row": index // 2, "column": index % 2, "group_id": group_id, "align": "effective-top-left"}
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    approve_bounds_then_figure(manifest_path)

    with pytest.raises(PharmFigError, match="shared effective-top-left"):
        workflow._layout(load_manifest(manifest_path))


def test_outputs_keep_helper_paths_nonexport_and_legacy_captions_uppercase(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_content_image(source / "panel.png")
    manifest_path = scan_folder(source, run, "nonexport")
    manifest = load_manifest(manifest_path)
    del manifest["journal"]["label_style"]
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    approve_bounds_then_figure(manifest_path)

    outputs = assemble_manifest(manifest_path)
    jsx = outputs["jsx"].read_text(encoding="utf-8-sig")
    svg = outputs["preview"].read_text(encoding="utf-8")
    caption = build_captions(manifest_path)["en"].read_text(encoding="utf-8")

    assert "layers['07_NOTES_NONEXPORT'].printable = false" in jsx
    assert 'stroke="#555"' not in svg
    assert caption.startswith("A ")


def test_qa_groups_same_size_measurements_and_names_internal_blank_area(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    for name in ("one.png", "two.png", "three.png", "four.png"):
        make_content_image(source / name)
    manifest_path = scan_folder(source, run, "qa-groups")
    manifest = load_manifest(manifest_path)
    for index, panel in enumerate(manifest["panels"]):
        group = "first" if index < 2 else "second"
        panel.update(label=chr(ord("a") + index), same_size_group=group, size_basis="effective_content", target_effective_width_mm=20 if group == "first" else 40)
        panel["layout"] = {"row": index // 2, "column": index % 2, "group_id": group, "align": "center"}
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    approve_bounds_then_figure(manifest_path)

    qa = run_qa(manifest_path).read_text(encoding="utf-8")

    assert "same-size（first）" in qa
    assert "same-size（second）" in qa
    assert "最大连续空白区域" in qa
    assert "配置gap" in qa
    assert "实测gap" in qa
    assert "标签布局坐标一致性" in qa


@pytest.mark.parametrize(
    ("fixture_name", "dimensions"),
    [
        ("microscopy-plus-quant", [(200, 100), (200, 100)]),
        ("multirow-microscopy-matrix", [(120, 80), (120, 80), (120, 80), (120, 80)]),
        ("flow-matrix-plus-bars", [(160, 100), (160, 100), (160, 100), (160, 100)]),
        ("animal-pathology-survival", [(180, 120), (180, 120), (180, 120), (220, 110)]),
        ("spectral-tem-bars-timeline", [(200, 100), (100, 100), (160, 100), (200, 80)]),
    ],
)
def test_visual_regression_fixtures_share_svg_jsx_coordinates_and_thresholds(
    tmp_path: Path, fixture_name: str, dimensions: list[tuple[int, int]]
):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    for index, dimension in enumerate(dimensions):
        make_image(source / f"panel-{index}.png", size=dimension)
    manifest_path = scan_folder(source, run, fixture_name)
    manifest = load_manifest(manifest_path)
    topologies = {
        "microscopy-plus-quant": [(0, 0, 1, 1), (0, 1, 1, 1)],
        "multirow-microscopy-matrix": [(0, 0, 1, 1), (0, 1, 1, 1), (1, 0, 1, 1), (1, 1, 1, 1)],
        "flow-matrix-plus-bars": [(0, 0, 1, 2), (0, 1, 1, 1), (1, 1, 1, 1), (2, 0, 2, 1)],
        "animal-pathology-survival": [(0, 0, 2, 1), (1, 0, 1, 1), (1, 1, 1, 1), (2, 0, 2, 1)],
        "spectral-tem-bars-timeline": [(0, 0, 2, 1), (1, 0, 1, 1), (1, 1, 1, 1), (2, 0, 2, 1)],
    }
    for index, panel in enumerate(manifest["panels"]):
        row, column, column_span, row_span = topologies[fixture_name][index]
        basis = "plot_area" if fixture_name == "flow-matrix-plus-bars" else "effective_content"
        panel.update(label=chr(ord("a") + index), same_size_group="fixture-images", size_basis=basis, target_effective_width_mm=24)
        if basis == "plot_area":
            panel["plot_area"] = {"normalized": [0, 0, 1, 1], "status": "approved"}
        panel["layout"] = {"row": row, "column": column, "column_span": column_span, "row_span": row_span, "group_id": "fixture-images", "align": "effective-top-left"}
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    approve_bounds_then_figure(manifest_path)

    boxes, _ = workflow._layout(load_manifest(manifest_path))
    outputs = assemble_manifest(manifest_path)
    svg = outputs["preview"].read_text(encoding="utf-8")
    jsx = outputs["jsx"].read_text(encoding="utf-8-sig")

    for box in boxes:
        assert f'<image x="{box["x"]}" y="{box["y"]}" width="{box["w"]}" height="{box["h"]}"' in svg
        assert f"var contentLeft = {box['x']} * MM" in jsx
        assert f"({workflow._layout(load_manifest(manifest_path))[1]} - {box['y']}) * MM" in jsx
        assert box["same_size_residual_percent"] <= 2
    assert "label.position = [contentLeft + -2 * MM, contentTop + 1.5 * MM]" in jsx
    assert max(abs(box["basis_w"] - 24) for box in boxes) <= 0.48


def test_unknown_scientific_panels_use_a_visible_printable_content_layer(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_content_image(source / "unknown.png")
    manifest_path = scan_folder(source, run, "visible-unknown")
    manifest = load_manifest(manifest_path)
    manifest["panels"][0]["label"] = "a"
    manifest["panels"][0]["content_guess"] = "unknown scientific panel"
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    approve_bounds_then_figure(manifest_path)

    jsx = assemble_manifest(manifest_path)["jsx"].read_text(encoding="utf-8-sig")

    assert "08_UNCLASSIFIED_CONTENT" in jsx
    assert "layers['08_UNCLASSIFIED_CONTENT'].groupItems.add(); var item" in jsx
    assert "layers['07_NOTES_NONEXPORT'].groupItems.add(); var item" not in jsx


def test_span_alignment_rejects_column_reading_order_reversal(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_content_image(source / "a.png")
    make_content_image(source / "b.png")
    manifest_path = scan_folder(source, run, "span-overlap")
    manifest = load_manifest(manifest_path)
    for index, panel in enumerate(manifest["panels"]):
        panel.update(label=chr(ord("a") + index), same_size_group="targets", size_basis="effective_content", target_effective_width_mm=30)
    manifest["panels"][0]["layout"] = {"row": 0, "column": 0, "column_span": 2, "group_id": "left", "align": "end"}
    manifest["panels"][1]["layout"] = {"row": 0, "column": 2, "group_id": "right", "align": "effective-top-left"}
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    approve_bounds_then_figure(manifest_path)

    with pytest.raises(PharmFigError, match="column reading order"):
        assemble_manifest(manifest_path)


def test_row_span_side_neighbors_reject_conflicting_local_gaps_and_qa_names_each_edge(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_image(source / "a.png", size=(100, 200))
    make_content_image(source / "b.png")
    make_content_image(source / "c.png")
    manifest_path = scan_folder(source, run, "span-side-gaps")
    manifest = load_manifest(manifest_path)
    layouts = ((0, 0, 1, 2, "shared"), (0, 1, 1, 1, "shared"), (1, 1, 1, 1, "different"))
    for index, (panel, (row, column, column_span, row_span, group_id)) in enumerate(zip(manifest["panels"], layouts)):
        panel.update(label=chr(ord("a") + index), same_size_group="side-panels", size_basis="effective_content", target_effective_width_mm=25)
        panel["layout"] = {"row": row, "column": column, "column_span": column_span, "row_span": row_span, "group_id": group_id, "align": "effective-top-left"}
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    approve_bounds_then_figure(manifest_path)

    with pytest.raises(PharmFigError, match="row-span local gaps"):
        workflow._layout(load_manifest(manifest_path))
    qa = run_qa(manifest_path).read_text(encoding="utf-8")
    assert "a-b" in qa
    assert "a-c" in qa


def test_right_row_span_side_neighbors_reject_conflicting_local_gaps_and_qa_names_each_edge(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    make_content_image(source / "a.png")
    make_content_image(source / "b.png")
    make_image(source / "c.png", size=(100, 200))
    manifest_path = scan_folder(source, run, "right-span-side-gaps")
    manifest = load_manifest(manifest_path)
    layouts = ((0, 0, 1, 1, "shared"), (1, 0, 1, 1, "different"), (0, 1, 1, 2, "shared"))
    for index, (panel, (row, column, column_span, row_span, group_id)) in enumerate(zip(manifest["panels"], layouts)):
        panel.update(label=chr(ord("a") + index), same_size_group="side-panels", size_basis="effective_content", target_effective_width_mm=25)
        panel["layout"] = {"row": row, "column": column, "column_span": column_span, "row_span": row_span, "group_id": group_id, "align": "effective-top-left"}
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    approve_bounds_then_figure(manifest_path)

    with pytest.raises(PharmFigError, match="row-span local gaps"):
        workflow._layout(load_manifest(manifest_path))
    qa = run_qa(manifest_path).read_text(encoding="utf-8")
    assert "a-c" in qa
    assert "b-c" in qa


def test_vertical_mixed_groups_get_local_content_edge_gaps_or_are_rejected(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    for name in ("a.png", "b.png", "c.png", "d.png"):
        make_content_image(source / name)
    manifest_path = scan_folder(source, run, "vertical-mixed")
    manifest = load_manifest(manifest_path)
    groups = ("left", "right-top", "left", "right-bottom")
    for index, (panel, group) in enumerate(zip(manifest["panels"], groups)):
        panel.update(label=chr(ord("a") + index), same_size_group="all", size_basis="effective_content", target_effective_width_mm=25)
        panel["layout"] = {"row": index // 2, "column": index % 2, "group_id": group, "align": "effective-top-left"}
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    approve_bounds_then_figure(manifest_path)

    boxes, _ = workflow._layout(load_manifest(manifest_path))

    left_gap = boxes[2]["y"] - (boxes[0]["y"] + boxes[0]["h"])
    right_gap = boxes[3]["y"] - (boxes[1]["y"] + boxes[1]["h"])
    assert left_gap == pytest.approx(1.8, abs=0.3)
    assert right_gap == pytest.approx(4.5, abs=0.3)


def test_qa_reports_only_adjacent_gaps_and_flags_final_overlap(tmp_path: Path):
    source = tmp_path / "source"
    run = tmp_path / "run"
    source.mkdir()
    for name in ("a.png", "b.png", "c.png"):
        make_content_image(source / name)
    manifest_path = scan_folder(source, run, "adjacent-gaps")
    manifest = load_manifest(manifest_path)
    for index, panel in enumerate(manifest["panels"]):
        panel.update(label=chr(ord("a") + index), same_size_group="line", size_basis="effective_content", target_effective_width_mm=20)
        panel["layout"] = {"row": 0, "column": index, "group_id": "line", "align": "effective-top-left"}
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    approve_bounds_then_figure(manifest_path)

    qa = run_qa(manifest_path).read_text(encoding="utf-8")

    assert "组内=1.80, 1.80 mm" in qa
    assert "41.80" not in qa
