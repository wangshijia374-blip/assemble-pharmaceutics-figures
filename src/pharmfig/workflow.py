from __future__ import annotations

import csv
import base64
import hashlib
import html
import io
import json
import math
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from PIL import Image, ImageChops, ImageDraw, UnidentifiedImageError


SUPPORTED = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".pdf", ".svg", ".eps"}
RASTER_SUPPORTED = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
PLACEHOLDER_ZH = "[待确认]"
PLACEHOLDER_EN = "[TO CONFIRM]"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEMANTIC_LAYERS = {
    "08_UNCLASSIFIED_CONTENT",
    "03_STATISTICAL_PLOTS",
    "04_MICROSCOPY",
    "05_SCHEMATICS",
    "07_NOTES_NONEXPORT",
}


class PharmFigError(RuntimeError):
    pass


class ApprovalError(PharmFigError):
    pass


class PrivacyError(PharmFigError):
    pass


def _validate_run_id(run_id: str) -> str:
    candidate = Path(run_id)
    if (
        not run_id
        or candidate.is_absolute()
        or candidate.drive
        or candidate.root
        or len(candidate.parts) != 1
        or run_id in {".", ".."}
        or "/" in run_id
        or "\\" in run_id
    ):
        raise PharmFigError("The run ID must be one relative filename component, not an absolute or traversal path.")
    return run_id


def _project_path(path: str | Path) -> Path:
    resolved = Path(path).resolve()
    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise PharmFigError(f"Output path is outside project root {PROJECT_ROOT}: {resolved}") from exc
    return resolved


def _output_folder(manifest: dict[str, Any]) -> Path:
    if "output_folder" not in manifest:
        raise PharmFigError("Manifest is missing output_folder.")
    if "run_id" in manifest:
        _validate_run_id(str(manifest["run_id"]))
    return _project_path(manifest["output_folder"])


def _artifact_path(output: Path, name: str | Path) -> Path:
    validated_output = _project_path(output)
    target = _project_path(validated_output / name)
    try:
        target.relative_to(validated_output)
    except ValueError as exc:
        raise PharmFigError(f"Artifact path escapes its output folder: {target}") from exc
    return target


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _image_info(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {
        "width_px": None,
        "height_px": None,
        "dpi": None,
        "read_error": None,
        "local_visual_summary": None,
    }
    if path.suffix.lower() not in RASTER_SUPPORTED:
        return info
    try:
        with Image.open(path) as image:
            info["width_px"], info["height_px"] = image.size
            dpi = image.info.get("dpi")
            if isinstance(dpi, tuple) and dpi:
                info["dpi"] = round(float(dpi[0]), 2)
            sample = image.convert("L")
            sample.thumbnail((64, 64))
            values = list(sample.get_flattened_data())
            mean = sum(values) / max(1, len(values))
            variance = sum((value - mean) ** 2 for value in values) / max(1, len(values))
            aspect = image.width / max(1, image.height)
            shape = "wide" if aspect > 1.5 else "tall" if aspect < 0.67 else "standard"
            info["local_visual_summary"] = {
                "shape": shape,
                "mean_luminance": round(mean, 2),
                "contrast_sd": round(math.sqrt(variance), 2),
            }
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        info["read_error"] = type(exc).__name__
    return info


def _default_content_bounds() -> dict[str, Any]:
    return {
        "mode": "manual",
        "normalized": [0.0, 0.0, 1.0, 1.0],
        "padding_percent": 2,
        "status": "draft",
        "detection_basis": "manual",
        "unresolved_risks": ["Content boundary has not been reviewed."],
    }


def _padded_normalized_bbox(
    bbox: tuple[int, int, int, int], width: int, height: int, padding_percent: float
) -> list[float]:
    left, top, right, bottom = bbox
    pad_x = (right - left) * padding_percent / 100
    pad_y = (bottom - top) * padding_percent / 100
    return [
        round(max(0.0, (left - pad_x) / width), 6),
        round(max(0.0, (top - pad_y) / height), 6),
        round(min(1.0, (right + pad_x) / width), 6),
        round(min(1.0, (bottom + pad_y) / height), 6),
    ]


def _detect_raster_content_bounds(path: Path, padding_percent: float = 2) -> dict[str, Any]:
    risks: list[str] = []
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        width, height = rgba.size
        alpha = rgba.getchannel("A")
        alpha_min, alpha_max = alpha.getextrema()
        if alpha_min < 255 and alpha_max > 0:
            mask = alpha.point(lambda value: 255 if value > 0 else 0)
            bbox = mask.getbbox()
            basis = "alpha"
        else:
            rgb = rgba.convert("RGB")
            step_x = max(1, width // 128)
            step_y = max(1, height // 128)
            border = []
            for x in range(0, width, step_x):
                border.extend((rgb.getpixel((x, 0)), rgb.getpixel((x, height - 1))))
            for y in range(0, height, step_y):
                border.extend((rgb.getpixel((0, y)), rgb.getpixel((width - 1, y))))
            channels = list(zip(*border))
            background = tuple(sorted(channel)[len(channel) // 2] for channel in channels)
            difference = ImageChops.difference(rgb, Image.new("RGB", rgb.size, background))
            red, green, blue = difference.split()
            strongest = ImageChops.lighter(ImageChops.lighter(red, green), blue)
            mask = strongest.point(lambda value: 255 if value > 12 else 0)
            bbox = mask.getbbox()
            basis = "border_color"
        if bbox is None:
            bbox = (0, 0, width, height)
            risks.append("No foreground distinct from the outer background was detected; review manually.")
        content_fraction = ((bbox[2] - bbox[0]) * (bbox[3] - bbox[1])) / max(1, width * height)
        if content_fraction > 0.98:
            risks.append("Detected content occupies nearly the full canvas; verify that the background is intentional.")
        if content_fraction < 0.01:
            risks.append("Detected content is very small; verify that labels, scale bars, and axes are included.")
        return {
            "mode": "manual",
            "normalized": _padded_normalized_bbox(bbox, width, height, padding_percent),
            "padding_percent": padding_percent,
            "status": "draft",
            "detection_basis": basis,
            "unresolved_risks": risks,
        }


def _classify(name: str) -> tuple[str, str, str, int]:
    text = name.lower()
    rules = [
        (("scheme", "schematic", "workflow", "timeline", "流程", "示意"), "实验设计或示意图", "建立阅读起点", 0),
        (("size", "zeta", "tem", "sem", "dls", "release", "粒径", "电位", "释放"), "材料或制剂表征", "先交代制剂性质", 1),
        (("microscopy", "fluorescence", "confocal", "he", "ihc", "if", "荧光", "病理"), "代表性图像", "展示代表性现象", 2),
        (("quant", "intensity", "score", "area", "定量"), "对应定量", "紧邻代表图提供定量支撑", 3),
        (("cfu", "colony", "viability", "mic", "菌落", "抑菌"), "体外功能结果", "展示体外功能证据", 4),
        (("survival", "weight", "efficacy", "tumor", "animal", "生存", "体重", "动物"), "动物药效", "展示体内治疗结局", 5),
        (("distribution", "biodistribution", "organ", "brain", "lung", "分布", "组织"), "分布或组织学", "连接体内分布与组织证据", 6),
        (("pca", "volcano", "heatmap", "transcript", "rna", "转录组", "火山图", "热图"), "组学概况", "展示整体组学变化", 7),
        (("kegg", "go_", "gsea", "pathway", "enrichment", "通路", "富集"), "通路分析", "从组学结果定位候选通路", 8),
        (("western", "blot", "wb", "qpcr", "validation", "验证"), "机制验证", "在末端验证候选机制", 9),
    ]
    for words, guess, reason, rank in rules:
        if any(word in text for word in words):
            return guess, reason, "中", rank
    return "待确认", "文件名和本地特征不足，需用户说明", "低", 99


def _declared_with_live_sources(value: Any) -> Any:
    if isinstance(value, list):
        return [_declared_with_live_sources(item) for item in value]
    if not isinstance(value, dict):
        return value
    declared = {
        key: _declared_with_live_sources(item)
        for key, item in value.items()
        if key not in {"source_fingerprint", "cloud_vision_authorized"}
    }
    source_value = value.get("source")
    if isinstance(source_value, str):
        source = Path(source_value)
        current = {"exists": source.exists(), "size": None, "mtime_ns": None, "sha256": None}
        if source.exists() and source.is_file():
            stat = source.stat()
            current.update(size=stat.st_size, mtime_ns=stat.st_mtime_ns, sha256=_sha256(source))
        declared["source"] = str(source.resolve())
        declared["current_source"] = current
    return declared


def _panel_fingerprint(panel: dict[str, Any]) -> dict[str, Any]:
    # This recursively fingerprints declared child sources and future layout
    # fields, rather than relying on a schema-specific allow-list.
    return _declared_with_live_sources(panel)


def manifest_hash(manifest: dict[str, Any]) -> str:
    payload = {
        key: _declared_with_live_sources(value)
        for key, value in manifest.items()
        if key != "approval" and key != "panels"
    }
    payload["panels"] = [_panel_fingerprint(panel) for panel in manifest.get("panels", [])]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path)
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise PharmFigError("Manifest must contain a YAML mapping")
    return data


def save_manifest(path: str | Path, manifest: dict[str, Any]) -> None:
    _output_folder(manifest)
    target = _project_path(path)
    target.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _validate_normalized_bounds(bounds: Any) -> list[float]:
    if not isinstance(bounds, list) or len(bounds) != 4:
        raise ApprovalError("Each panel must have four normalized content bounds values.")
    try:
        left, top, right, bottom = (float(value) for value in bounds)
    except (TypeError, ValueError) as exc:
        raise ApprovalError("Content bounds must be numeric normalized values.") from exc
    if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
        raise ApprovalError("Content bounds must satisfy 0 <= left < right <= 1 and 0 <= top < bottom <= 1.")
    return [left, top, right, bottom]


def detect_content_bounds(manifest_path: str | Path) -> dict[str, Path]:
    path = Path(manifest_path)
    manifest = load_manifest(path)
    output = _output_folder(manifest)
    output.mkdir(parents=True, exist_ok=True)
    review_cards: list[tuple[str, Image.Image, list[float], str, list[str]]] = []
    for panel in manifest.get("panels", []):
        source = Path(panel["source"])
        if source.suffix.lower() in RASTER_SUPPORTED:
            try:
                bounds = _detect_raster_content_bounds(source, 2)
                with Image.open(source) as image:
                    rgba = image.convert("RGBA")
                    flattened = Image.new("RGBA", rgba.size, "white")
                    flattened.alpha_composite(rgba)
                    review_image = flattened.convert("RGB")
            except (UnidentifiedImageError, OSError, ValueError) as exc:
                bounds = _default_content_bounds()
                bounds["unresolved_risks"] = [f"Raster could not be analyzed ({type(exc).__name__}); set bounds manually."]
                review_image = Image.new("RGB", (800, 500), "white")
        else:
            bounds = _default_content_bounds()
            bounds["unresolved_risks"] = ["Vector/PDF bounds require manual review in Illustrator."]
            review_image = Image.new("RGB", (800, 500), "white")
        panel["content_bounds"] = bounds
        review_cards.append(
            (str(panel.get("label") or panel.get("id")), review_image, bounds["normalized"], bounds["detection_basis"], bounds["unresolved_risks"])
        )
    manifest["approval"] = {"status": "draft", "approved_at": None, "approved_panel_order": [], "manifest_hash": None}
    save_manifest(path, manifest)

    card_w, card_h, columns = 800, 600, 2
    rows = max(1, math.ceil(len(review_cards) / columns))
    sheet = Image.new("RGB", (card_w * columns, card_h * rows), "white")
    draw_sheet = ImageDraw.Draw(sheet)
    for index, (label, image, normalized, basis, risks) in enumerate(review_cards):
        image.thumbnail((740, 500))
        x0 = (index % columns) * card_w + 30
        y0 = (index // columns) * card_h + 60
        sheet.paste(image, (x0, y0))
        left, top, right, bottom = normalized
        draw_sheet.rectangle(
            (
                x0 + round(left * image.width),
                y0 + round(top * image.height),
                x0 + round(right * image.width),
                y0 + round(bottom * image.height),
            ),
            outline=(220, 20, 60),
            width=4,
        )
        draw_sheet.text((x0, y0 - 45), f"{label.upper()}  basis={basis}", fill="black")
        if risks:
            draw_sheet.text((x0, y0 + image.height + 8), "MANUAL REVIEW REQUIRED", fill=(180, 0, 0))
    review_png = _artifact_path(output, "content_bounds_review.png")
    sheet.save(review_png, dpi=(150, 150))
    review_md = _artifact_path(output, "content_bounds_review.md")
    lines = ["# Content bounds review", "", "Red rectangles are candidates only. Confirm every panel before assembly.", ""]
    for panel in manifest.get("panels", []):
        bounds = panel["content_bounds"]
        risks = "; ".join(bounds.get("unresolved_risks") or []) or "None"
        lines.append(
            f"- {str(panel.get('label') or panel.get('id')).upper()}: normalized={bounds['normalized']}; "
            f"padding={bounds['padding_percent']}%; basis={bounds['detection_basis']}; risks={risks}"
        )
    review_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"review_png": review_png, "review_md": review_md}


def approve_content_bounds(manifest_path: str | Path) -> None:
    path = Path(manifest_path)
    manifest = load_manifest(path)
    if not manifest.get("panels"):
        raise ApprovalError("Cannot approve content bounds without panels.")
    for panel in manifest["panels"]:
        bounds = panel.get("content_bounds")
        if not isinstance(bounds, dict):
            raise ApprovalError(f"Panel {panel.get('label') or panel.get('id')} has no content bounds proposal.")
        bounds["normalized"] = _validate_normalized_bounds(bounds.get("normalized"))
        bounds["mode"] = "manual"
        bounds["status"] = "approved"
        bounds["detection_basis"] = bounds.get("detection_basis") or "manual"
        bounds["unresolved_risks"] = list(bounds.get("unresolved_risks") or [])
    manifest["approval"] = {"status": "draft", "approved_at": None, "approved_panel_order": [], "manifest_hash": None}
    save_manifest(path, manifest)


def scan_folder(source_folder: str | Path, run_folder: str | Path, run_id: str) -> Path:
    _validate_run_id(run_id)
    source = Path(source_folder).resolve()
    run = _project_path(run_folder)
    if not source.is_dir():
        raise PharmFigError(f"Input folder does not exist: {source}")
    run.mkdir(parents=True, exist_ok=True)
    files = sorted((p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED), key=lambda p: p.name.lower())
    panels = []
    for index, path in enumerate(files):
        guess, reason, confidence, rank = _classify(path.name)
        stat = path.stat()
        panels.append({
            "id": f"panel-{index + 1:03d}",
            "label": "",
            "source": str(path.resolve()),
            "relative_source": str(path.relative_to(source)),
            "extension": path.suffix.lower(),
            **_image_info(path),
            "source_fingerprint": {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "sha256": _sha256(path)},
            "content_guess": guess,
            "reason": reason,
            "confidence": confidence,
            "narrative_rank": rank,
            "group": None,
            "cloud_vision_authorized": False,
            "content_bounds": _default_content_bounds(),
            "caption_facts": {"zh": PLACEHOLDER_ZH, "en": PLACEHOLDER_EN},
        })
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at": _now(),
        "source_folder": str(source),
        "output_folder": str(run),
        "figure": {"number": "Figure X", "core_conclusion": "待用户确认：本Figure的唯一核心结论"},
        "journal": {
            "profile": "compact-journal-v1",
            "compactness_profile": "compact-journal-v1",
            "artboard_width_mm": 210,
            "artboard_height_mm": 297,
            "orientation": "portrait",
            "width_mm": 210,
            "auto_height": False,
            "font": "Arial",
            "minimum_font_pt": 7,
            "label_style": "A",
            "label_font_pt": 8,
            "label_offset_x_mm": -2,
            "label_offset_y_mm": -1.5,
            "intra_gap_mm": 1.8,
            "inter_gap_mm": 4.5,
            "gap_mm": 4.5,
            "margin_mm": 4,
        },
        "panels": panels,
        "approval": {"status": "draft", "approved_at": None, "approved_panel_order": [], "manifest_hash": None},
    }
    manifest_path = run / "manifest.yaml"
    save_manifest(manifest_path, manifest)
    return manifest_path


def prepare_cloud_thumbnails(
    manifest_path: str | Path,
    panel_labels: list[str],
    *,
    confirm_upload: bool,
    confirm_content_safe: bool = False,
) -> list[Path]:
    """Create resized, filename-free local previews after explicit safety checks.

    Visible content and text remain in the pixels; no OCR redaction is performed.
    This function does not perform a network request. A caller may transport only
    the returned files, and only in the same user-approved operation.
    """
    if not confirm_upload:
        raise PrivacyError("Cloud analysis requires explicit confirmation for this operation.")
    if not confirm_content_safe:
        raise PrivacyError(
            "Cloud analysis requires a distinct acknowledgement that visible text/content was reviewed and is safe to transport."
        )
    manifest = load_manifest(manifest_path)
    output = _output_folder(manifest)
    selected = [panel for panel in manifest.get("panels", []) if panel.get("label") in panel_labels]
    if len(selected) != len(set(panel_labels)):
        raise PrivacyError("Every requested panel label must exist in the manifest.")
    if any(not panel.get("cloud_vision_authorized") for panel in selected):
        raise PrivacyError("Every requested panel must have cloud_vision_authorized: true.")
    output = _artifact_path(output, Path(".work") / "cloud-preview")
    output.mkdir(parents=True, exist_ok=True)
    thumbnails: list[Path] = []
    for index, panel in enumerate(selected, start=1):
        source = Path(panel["source"])
        if source.suffix.lower() not in RASTER_SUPPORTED:
            raise PrivacyError(f"Panel {panel['label']} cannot be made into a local raster preview in version 1.")
        target = _artifact_path(output, f"panel-{index:03d}.jpg")
        with Image.open(source) as image:
            copy = image.convert("RGB")
            copy.thumbnail((1600, 1600))
            copy.save(target, "JPEG", quality=88, optimize=True)
        thumbnails.append(target)
    return thumbnails


def _openai_transport(images: list[Path], prompt: str) -> list[dict[str, str]]:
    if not os.environ.get("OPENAI_API_KEY"):
        raise PrivacyError("OPENAI_API_KEY is not configured; no upload was attempted.")
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as exc:
        raise PrivacyError("Install the optional 'openai' package before cloud analysis.") from exc
    content: list[dict[str, str]] = [{"type": "input_text", "text": prompt}]
    for image in images:
        encoded = base64.b64encode(image.read_bytes()).decode("ascii")
        content.append({"type": "input_image", "image_url": f"data:image/jpeg;base64,{encoded}"})
    response = OpenAI().responses.create(model="gpt-5-mini", input=[{"role": "user", "content": content}])
    try:
        parsed = json.loads(response.output_text)
    except (AttributeError, json.JSONDecodeError) as exc:
        raise PharmFigError("Cloud vision returned an invalid structured response.") from exc
    if not isinstance(parsed, list):
        raise PharmFigError("Cloud vision response must be a JSON list.")
    return parsed


def analyze_cloud_panels(
    manifest_path: str | Path,
    panel_labels: list[str],
    *,
    confirm_upload: bool,
    confirm_content_safe: bool = False,
    transport: Any | None = None,
) -> list[dict[str, str]]:
    thumbnails = prepare_cloud_thumbnails(
        manifest_path,
        panel_labels,
        confirm_upload=confirm_upload,
        confirm_content_safe=confirm_content_safe,
    )
    labels = ", ".join(panel_labels)
    prompt = (
        "Analyze the following resized scientific-figure previews with local filenames removed. "
        "Visible text may remain because no OCR redaction was performed; the user reviewed it as safe to transport. "
        f"Their neutral panel labels are: {labels}. Do not infer treatment groups, sample size, "
        "statistics, biological identity, or causal conclusions. Return only a JSON list with "
        "label, content_guess, confidence (high/medium/low), and visible_features."
    )
    results = (transport or _openai_transport)(thumbnails, prompt)
    path = Path(manifest_path)
    manifest = load_manifest(path)
    by_label = {str(result.get("label")): result for result in results if isinstance(result, dict)}
    for panel in manifest.get("panels", []):
        result = by_label.get(panel.get("label"))
        if result:
            panel["content_guess"] = str(result.get("content_guess") or "待确认")
            raw_confidence = str(result.get("confidence") or "low").lower()
            panel["confidence"] = {"high": "高", "medium": "中", "low": "低"}.get(raw_confidence, "低")
            panel["reason"] = "可选云端视觉仅识别可见图形类型；科学含义仍需用户确认"
            panel["caption_facts"] = {"zh": PLACEHOLDER_ZH, "en": PLACEHOLDER_EN}
    manifest["approval"] = {"status": "draft", "approved_at": None, "approved_panel_order": [], "manifest_hash": None}
    save_manifest(path, manifest)
    return results


def _labels(count: int) -> list[str]:
    if count > 26:
        raise PharmFigError("Version 1 supports at most 26 top-level panels")
    return [chr(ord("a") + i) for i in range(count)]


def propose_manifest(manifest_path: str | Path, journal_path: str | Path | None = None) -> Path:
    path = Path(manifest_path)
    manifest = load_manifest(path)
    output = _output_folder(manifest)
    if journal_path:
        overrides = yaml.safe_load(Path(journal_path).read_text(encoding="utf-8")) or {}
        manifest["journal"].update(overrides)
    panels = sorted(manifest.get("panels", []), key=lambda panel: (panel.get("narrative_rank", 99), panel["relative_source"].lower()))
    for panel, label in zip(panels, _labels(len(panels))):
        panel["label"] = label
    manifest["panels"] = panels
    manifest["approval"] = {"status": "draft", "approved_at": None, "approved_panel_order": [], "manifest_hash": None}
    save_manifest(path, manifest)

    lines = [
        f"# {manifest['figure']['number']} 组图建议",
        "",
        "## 建议核心结论",
        manifest["figure"]["core_conclusion"],
        "",
        "## 建议面板顺序",
    ]
    for panel in panels:
        lines.append(f"- {panel['label']}. {panel['content_guess']}——{panel['reason']}")
    lines.extend([
        "",
        "## 排序逻辑",
        "实验设计 → 制剂表征 → 代表性现象 → 定量验证 → 体外功能 → 动物药效 → 分布/组织学 → 组学概况 → 通路分析 → 机制验证。",
        "",
        "| 面板 | 文件 | 内容判断 | 放置理由 | 置信度 |",
        "|---|---|---|---|---|",
    ])
    for panel in panels:
        lines.append(f"| {panel['label']} | {panel['relative_source']} | {panel['content_guess']} | {panel['reason']} | {panel['confidence']} |")
    lines.extend(["", "请确认、调序、替换、合并或删除面板。收到明确确认前不会调用Illustrator。"])
    proposal_path = _artifact_path(output, "proposal.md")
    proposal_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return proposal_path


def approve_manifest(manifest_path: str | Path) -> dict[str, Any]:
    path = Path(manifest_path)
    manifest = load_manifest(path)
    _output_folder(manifest)
    panels = manifest.get("panels", [])
    if not panels or any(not panel.get("label") for panel in panels):
        labels = _labels(len(panels))
        for panel, label in zip(panels, labels):
            panel["label"] = label
    manifest["approval"] = {
        "status": "approved",
        "approved_at": _now(),
        "approved_panel_order": [panel["label"] for panel in panels],
        "manifest_hash": None,
    }
    manifest["approval"]["manifest_hash"] = manifest_hash(manifest)
    save_manifest(path, manifest)
    return manifest


def _assert_approved(path: Path, manifest: dict[str, Any]) -> None:
    approval = manifest.get("approval", {})
    current_hash = manifest_hash(manifest)
    if approval.get("status") != "approved":
        raise ApprovalError("Manifest is not approved. Review proposal.md and run pharmfig approve first.")
    if approval.get("manifest_hash") != current_hash:
        approval["status"] = "revoked"
        approval["approved_at"] = None
        manifest["approval"] = approval
        save_manifest(path, manifest)
        raise ApprovalError("Approval was revoked because panel order, facts, settings, or source files changed.")


def _assert_content_bounds_approved(manifest: dict[str, Any]) -> None:
    missing = []
    for panel in manifest.get("panels", []):
        bounds = panel.get("content_bounds")
        if not isinstance(bounds, dict) or bounds.get("status") != "approved":
            missing.append(str(panel.get("label") or panel.get("id")))
            continue
        _validate_normalized_bounds(bounds.get("normalized"))
    if missing:
        raise ApprovalError(
            "All panel content bounds require manual approval before assembly; pending content bounds: " + ", ".join(missing)
        )


def _label_text(label: str, style: str) -> str:
    if style == "A":
        return label.upper()
    if style == "(a)":
        return f"({label})"
    if style == "a,":
        return f"{label},"
    return f"{label}."


def _jsx_escape(value: str) -> str:
    return value.replace("\\", "/").replace('"', '\\"')


def _panel_layer(panel: dict[str, Any]) -> str:
    override = panel.get("layer_override")
    if isinstance(override, str) and override in SEMANTIC_LAYERS:
        return override
    guess = str(panel.get("content_guess") or "").lower()
    if any(word in guess for word in ("schematic", "scheme", "workflow", "timeline", "示意", "实验设计")):
        return "05_SCHEMATICS"
    if any(
        word in guess
        for word in (
            "representative image",
            "microscopy",
            "histology",
            "fluorescence",
            "confocal",
            "代表性图像",
            "组织学",
            "病理",
            "荧光",
        )
    ):
        return "04_MICROSCOPY"
    if any(
        word in guess
        for word in (
            "plot",
            "statistical",
            "chart",
            "quant",
            "pca",
            "volcano",
            "heatmap",
            "enrichment",
            "pathway",
            "定量",
            "组学概况",
            "通路分析",
        )
    ):
        return "03_STATISTICAL_PLOTS"
    return "08_UNCLASSIFIED_CONTENT"


def _basis_geometry(panel: dict[str, Any], basis: str) -> dict[str, float] | None:
    """Approved content/plot geometry, expressed relative to effective content."""
    content = _validate_normalized_bounds(panel["content_bounds"]["normalized"])
    selected = content
    if basis == "plot_area":
        plot_area = panel.get("plot_area")
        if not isinstance(plot_area, dict) or plot_area.get("status") != "approved":
            return None
        selected = _validate_normalized_bounds(plot_area.get("normalized"))
        if not (content[0] <= selected[0] < selected[2] <= content[2] and content[1] <= selected[1] < selected[3] <= content[3]):
            raise PharmFigError(f"Panel {panel.get('label')} approved plot_area must lie inside approved content_bounds.")
    width_px = float(panel.get("width_px") or 1)
    height_px = float(panel.get("height_px") or 1)
    content_w_px = width_px * (content[2] - content[0])
    content_h_px = height_px * (content[3] - content[1])
    basis_w_px = width_px * (selected[2] - selected[0])
    basis_h_px = height_px * (selected[3] - selected[1])
    return {
        "content_aspect": max(0.05, content_w_px / max(1.0, content_h_px)),
        "basis_aspect": max(0.05, basis_w_px / max(1.0, basis_h_px)),
        "basis_width_fraction": basis_w_px / max(1.0, content_w_px),
        "basis_height_fraction": basis_h_px / max(1.0, content_h_px),
    }


def _effective_aspect(panel: dict[str, Any]) -> float:
    geometry = _basis_geometry(panel, "effective_content")
    assert geometry is not None
    return geometry["content_aspect"]


def _layout_spec(panel: dict[str, Any], index: int, columns: int) -> dict[str, Any]:
    raw = panel.get("layout")
    if raw is None:
        return {"row": index // columns, "column": index % columns, "column_span": 1, "row_span": 1, "group_id": panel.get("group"), "align": "effective-top-left"}
    if not isinstance(raw, dict):
        raise PharmFigError(f"Panel {panel.get('label')} layout must be a mapping.")
    values: dict[str, Any] = {}
    for key, default in (("row", 0), ("column", 0), ("column_span", 1), ("row_span", 1)):
        value = raw.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or value < (1 if "span" in key else 0):
            raise PharmFigError(f"Panel {panel.get('label')} layout.{key} must be a non-negative integer" + (" greater than zero." if "span" in key else "."))
        values[key] = value
    group_id = raw.get("group_id", panel.get("group"))
    if group_id is not None and not isinstance(group_id, str):
        raise PharmFigError(f"Panel {panel.get('label')} layout.group_id must be a string or null.")
    align = raw.get("align", "center")
    if align not in {"start", "center", "end", "effective-top-left", "effective-top", "effective-left"}:
        raise PharmFigError(f"Panel {panel.get('label')} layout.align must be start, center, end, effective-top-left, effective-top, or effective-left.")
    values.update(group_id=group_id, align=align)
    return values


def _same_size_target(panels: list[dict[str, Any]], available_widths: list[float]) -> dict[int, dict[str, Any]]:
    """Choose approved basis targets; conflicting dimensions preserve aspect and report residuals."""
    targets: dict[int, dict[str, Any]] = {}
    groups: dict[str, list[int]] = {}
    for index, panel in enumerate(panels):
        group = panel.get("same_size_group")
        if group is not None:
            if not isinstance(group, str) or not group.strip():
                raise PharmFigError(f"Panel {panel.get('label')} same_size_group must be a non-empty string.")
            groups.setdefault(group, []).append(index)
    for indices in groups.values():
        bases = {str(panels[index].get("size_basis") or "effective_content") for index in indices}
        if len(bases) != 1 or not bases <= {"effective_content", "plot_area"}:
            raise PharmFigError("same_size_group members must share size_basis: effective_content or plot_area.")
        basis = bases.pop()
        explicit_width = [float(panels[index]["target_effective_width_mm"]) for index in indices if panels[index].get("target_effective_width_mm") is not None]
        explicit_height = [float(panels[index]["target_effective_height_mm"]) for index in indices if panels[index].get("target_effective_height_mm") is not None]
        for name, values in (("target_effective_width_mm", explicit_width), ("target_effective_height_mm", explicit_height)):
            if values and (any(value <= 0 for value in values) or max(values) - min(values) > 0.05):
                raise PharmFigError(f"same_size_group {name} values must be one positive common target.")
        geometry = [_basis_geometry(panels[index], basis) for index in indices]
        approved = all(item is not None for item in geometry)
        target_width = explicit_width[0] if explicit_width else None
        target_height = explicit_height[0] if explicit_height else None
        if approved and target_width is None and target_height is None:
            target_width = min(available_widths[index] * geometry[position]["basis_width_fraction"] for position, index in enumerate(indices))
        control = str(panels[indices[0]].get("size_control_dimension") or ("width" if target_width is not None else "height"))
        if control not in {"width", "height"}:
            raise PharmFigError("size_control_dimension must be width or height.")
        for index in indices:
            targets[index] = {"basis": basis, "target_width": target_width if approved else None, "target_height": target_height if approved else None, "control": control, "approved": approved}
    return targets


def _layout(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], float]:
    """Deterministic, content-aware top-level layout shared by SVG, JSX, and QA."""
    panels = manifest["panels"]
    journal = manifest["journal"]
    width_mm = float(journal.get("artboard_width_mm", journal.get("width_mm", 210)))
    height_limit = float(journal.get("artboard_height_mm", 297))
    margin = float(journal.get("margin_mm", 4))
    intra_gap = float(journal.get("intra_gap_mm", 1.8))
    inter_gap = float(journal.get("inter_gap_mm", journal.get("gap_mm", 4.5)))
    if width_mm <= 2 * margin or height_limit <= 2 * margin or min(intra_gap, inter_gap) < 0:
        raise PharmFigError("Artboard margins and compact-layout gaps must leave positive usable space.")
    for panel in panels:
        if panel.get("size_basis") is not None and panel["size_basis"] not in {"effective_content", "plot_area"}:
            raise PharmFigError(f"Panel {panel.get('label')} size_basis must be effective_content or plot_area.")
    count = len(panels)
    if not count:
        return [], height_limit
    fallback_columns = 1 if count == 1 else 2 if count <= 6 else 3
    specs = [_layout_spec(panel, index, fallback_columns) for index, panel in enumerate(panels)]
    columns = max(spec["column"] + spec["column_span"] for spec in specs)
    rows = max(spec["row"] + spec["row_span"] for spec in specs)
    occupied: set[tuple[int, int]] = set()
    for panel, spec in zip(panels, specs):
        for row in range(spec["row"], spec["row"] + spec["row_span"]):
            for column in range(spec["column"], spec["column"] + spec["column_span"]):
                if (row, column) in occupied:
                    raise PharmFigError(f"Panel {panel.get('label')} layout overlaps another panel.")
                occupied.add((row, column))

    default_cell_width = (width_mm - 2 * margin - (columns - 1) * inter_gap) / columns
    if default_cell_width <= 0:
        raise PharmFigError("Compact layout has no horizontal space after margins and inter-group gaps.")
    provisional_widths = [default_cell_width * spec["column_span"] + inter_gap * (spec["column_span"] - 1) for spec in specs]
    targets = _same_size_target(panels, provisional_widths)
    geometries = []
    for index, panel in enumerate(panels):
        basis = targets.get(index, {}).get("basis", "effective_content")
        geometry = _basis_geometry(panel, basis) or _basis_geometry(panel, "effective_content")
        assert geometry is not None
        geometries.append(geometry)

    def desired_content_size(index: int, available_width: float) -> tuple[float, float, float | None, float | None]:
        target = targets.get(index, {})
        geometry = geometries[index]
        target_width = target.get("target_width")
        target_height = target.get("target_height")
        control = target.get("control", "width")
        if target_width is not None and (target_height is None or control == "width"):
            content_width = target_width / geometry["basis_width_fraction"]
        elif target_height is not None:
            content_width = (target_height / geometry["basis_height_fraction"]) * geometry["content_aspect"]
        else:
            content_width = available_width
        return content_width, content_width / geometry["content_aspect"], target_width, target_height

    # Track widths are content-driven for declared same-size groups. Untargeted columns retain
    # the deterministic fallback width, while target widths eliminate unused slot whitespace.
    column_widths = [default_cell_width] * columns
    targeted_column = [False] * columns
    for index, spec in enumerate(specs):
        if spec["column_span"] == 1 and targets.get(index, {}).get("target_width") is not None or (spec["column_span"] == 1 and targets.get(index, {}).get("target_height") is not None):
            content_width, _, _, _ = desired_content_size(index, default_cell_width)
            column_widths[spec["column"]] = max(1.0, content_width)
            targeted_column[spec["column"]] = True

    def local_gap(first: dict[str, Any], second: dict[str, Any]) -> float:
        first_group, second_group = first.get("group_id"), second.get("group_id")
        return intra_gap if first_group and first_group == second_group else inter_gap

    # Vertical tracks satisfy every span instead of placing all its height in its first row.
    row_gaps = [inter_gap] * max(0, rows - 1)
    for row in range(rows - 1):
        touching = [
            (left, right) for left in specs for right in specs
            if left["row"] + left["row_span"] - 1 == row and right["row"] == row + 1
            and max(left["column"], right["column"]) < min(left["column"] + left["column_span"], right["column"] + right["column_span"])
        ]
        if touching and all(left.get("group_id") and left.get("group_id") == right.get("group_id") for left, right in touching):
            row_gaps[row] = intra_gap
    row_heights = [1.0] * rows
    for _ in range(rows + 1):
        changed = False
        for index, spec in enumerate(specs):
            span_width = sum(column_widths[spec["column"] : spec["column"] + spec["column_span"]]) + inter_gap * (spec["column_span"] - 1)
            _, desired_height, _, _ = desired_content_size(index, span_width)
            current_height = sum(row_heights[spec["row"] : spec["row"] + spec["row_span"]]) + sum(row_gaps[spec["row"] : spec["row"] + spec["row_span"] - 1])
            if desired_height > current_height + 1e-6:
                extra = (desired_height - current_height) / spec["row_span"]
                for row in range(spec["row"], spec["row"] + spec["row_span"]):
                    row_heights[row] += extra
                changed = True
        if not changed:
            break
    row_tops: list[float] = []
    cursor = margin
    for row, height in enumerate(row_heights):
        row_tops.append(cursor)
        cursor += height + (row_gaps[row] if row < rows - 1 else 0)
    required_height_mm = cursor + margin
    if journal.get("auto_height", False):
        height_mm = required_height_mm
    else:
        height_mm = height_limit
        if required_height_mm > height_mm + 1e-6:
            raise PharmFigError(
                f"Panels require {required_height_mm:.1f} mm height, exceeding the {height_mm:.1f} mm artboard; revise the approved layout or split the figure."
            )
    positions: list[dict[str, Any]] = []
    row_positions: dict[int, list[tuple[int, dict[str, Any]]]] = {}
    for index, spec in enumerate(specs):
        row_positions.setdefault(spec["row"], []).append((index, spec))
    x_by_index: dict[int, float] = {}
    for row, items in row_positions.items():
        previous: tuple[int, dict[str, Any], float] | None = None
        for index, spec in sorted(items, key=lambda item: item[1]["column"]):
            span_width = sum(column_widths[spec["column"] : spec["column"] + spec["column_span"]]) + inter_gap * (spec["column_span"] - 1)
            content_width, _, _, _ = desired_content_size(index, span_width)
            if previous is None:
                aligned = [x_by_index[other_index] for other_index, other_spec in enumerate(specs) if other_index in x_by_index and other_spec["column"] == spec["column"]]
                x = aligned[0] if aligned else margin + sum(column_widths[: spec["column"]]) + inter_gap * spec["column"]
            else:
                previous_index, previous_spec, previous_x = previous
                previous_width, _, _, _ = desired_content_size(previous_index, sum(column_widths[previous_spec["column"] : previous_spec["column"] + previous_spec["column_span"]]) + inter_gap * (previous_spec["column_span"] - 1))
                x = previous_x + previous_width + local_gap(previous_spec, spec)
            x_by_index[index] = x
            previous = (index, spec, x)
    max_right = max(x_by_index[index] + desired_content_size(index, sum(column_widths[spec["column"] : spec["column"] + spec["column_span"]]) + inter_gap * (spec["column_span"] - 1))[0] for index, spec in enumerate(specs))
    if max_right + margin > width_mm + 1e-6:
        raise PharmFigError(f"Panels require {max_right + margin:.1f} mm width, exceeding the {width_mm:.1f} mm artboard; revise the layout or split the figure.")
    for index, (panel, spec) in enumerate(zip(panels, specs)):
        slot_x = x_by_index[index]
        slot_y = row_tops[spec["row"]]
        slot_w = sum(column_widths[spec["column"] : spec["column"] + spec["column_span"]]) + inter_gap * (spec["column_span"] - 1)
        slot_h = sum(row_heights[spec["row"] : spec["row"] + spec["row_span"]]) + sum(row_gaps[spec["row"] : spec["row"] + spec["row_span"] - 1])
        content_w, content_h, target_width, target_height = desired_content_size(index, slot_w)
        if content_h > slot_h + 1e-6:
            content_h = slot_h
            content_w = content_h * geometries[index]["content_aspect"]
        align = spec["align"]
        x = slot_x if align in {"start", "effective-top-left", "effective-left"} else slot_x + (slot_w - content_w if align == "end" else (slot_w - content_w) / 2)
        y = slot_y if align in {"effective-top-left", "effective-top"} else slot_y + (slot_h - content_h) / 2
        basis_w = content_w * geometries[index]["basis_width_fraction"]
        basis_h = content_h * geometries[index]["basis_height_fraction"]
        width_residual = 0.0 if target_width in (None, 0) else abs(basis_w - target_width) / target_width * 100
        height_residual = 0.0 if target_height in (None, 0) else abs(basis_h - target_height) / target_height * 100
        residual = max(width_residual, height_residual)
        target = targets.get(index, {})
        positions.append({
            "label": str(panel.get("label") or panel.get("id") or index + 1),
            "x": x, "y": y, "w": content_w, "h": content_h,
            "content_w": content_w, "content_h": content_h,
            "slot_w": slot_w, "slot_h": slot_h,
            "basis_w": basis_w, "basis_h": basis_h,
            "same_size_group": panel.get("same_size_group"),
            "same_size_target_mm": target_width, "same_size_target_width_mm": target_width, "same_size_target_height_mm": target_height, "same_size_basis": target.get("basis"),
            "same_size_residual_percent": residual,
            "same_size_width_residual_percent": width_residual,
            "same_size_height_residual_percent": height_residual,
            "group_id": spec["group_id"],
            "row": spec["row"], "column": spec["column"], "row_span": spec["row_span"], "column_span": spec["column_span"],
            "align": align,
        })
    # A mixed vertical boundary cannot use one global row gap without either wasting a
    # same-group column or collapsing a different-group column. Top-aligned single-cell
    # items therefore advance locally within their own column.
    for column in range(columns):
        column_items = [box for box in positions if box["column"] == column and box["column_span"] == 1 and box["row_span"] == 1]
        previous: dict[str, Any] | None = None
        for box in sorted(column_items, key=lambda item: item["row"]):
            if previous is not None and box["row"] == previous["row"] + 1 and box["align"] in {"effective-top-left", "effective-top"}:
                gap = intra_gap if previous.get("group_id") and previous.get("group_id") == box.get("group_id") else inter_gap
                box["y"] = previous["y"] + previous["h"] + gap
            previous = box
        top_left_items = [box for box in column_items if box["align"] == "effective-top-left"]
        if top_left_items and max(box["x"] for box in top_left_items) - min(box["x"] for box in top_left_items) > 0.3:
            raise PharmFigError(f"Column {column} cannot satisfy shared effective-top-left alignment and local content gaps; revise grouping or spans.")
    for index, first in enumerate(positions):
        for second in positions[index + 1:]:
            vertical_overlap = min(first["y"] + first["h"], second["y"] + second["h"]) - max(first["y"], second["y"])
            if vertical_overlap <= 1e-6:
                continue
            if first["column"] + first["column_span"] <= second["column"] and first["x"] > second["x"] + 0.3:
                raise PharmFigError(f"Final column reading order reverses approved panels {first['label']} → {second['label']}; revise span alignment or targets.")
            if second["column"] + second["column_span"] <= first["column"] and second["x"] > first["x"] + 0.3:
                raise PharmFigError(f"Final column reading order reverses approved panels {second['label']} → {first['label']}; revise span alignment or targets.")
    span_gap_entries: list[str] = []
    span_gap_failed = False
    for first in positions:
        if first["row_span"] <= 1:
            continue
        for second in positions:
            if second is first:
                continue
            vertical_overlap = min(first["y"] + first["h"], second["y"] + second["h"]) - max(first["y"], second["y"])
            if vertical_overlap <= 1e-6:
                continue
            if second["column"] == first["column"] + first["column_span"]:
                edge_label = f"{first['label']}-{second['label']}"
                actual_gap = second["x"] - (first["x"] + first["w"])
            elif second["column"] + second["column_span"] == first["column"]:
                edge_label = f"{second['label']}-{first['label']}"
                actual_gap = first["x"] - (second["x"] + second["w"])
            else:
                continue
            expected_gap = intra_gap if first.get("group_id") and first.get("group_id") == second.get("group_id") else inter_gap
            span_gap_entries.append(f"{edge_label}={actual_gap:.2f} mm (expected {expected_gap:.2f} mm)")
            span_gap_failed = span_gap_failed or abs(actual_gap - expected_gap) > 0.3
    if span_gap_failed:
        raise PharmFigError("row-span local gaps cannot be satisfied independently: " + "; ".join(span_gap_entries))
    for index, first in enumerate(positions):
        for second in positions[index + 1:]:
            horizontal_overlap = min(first["x"] + first["w"], second["x"] + second["w"]) - max(first["x"], second["x"])
            vertical_overlap = min(first["y"] + first["h"], second["y"] + second["h"]) - max(first["y"], second["y"])
            if horizontal_overlap > 1e-6 and vertical_overlap > 1e-6:
                raise PharmFigError(f"Final effective-content overlap between panels {first['label']} and {second['label']}; revise span, target size, or alignment.")
    return positions, height_mm


def _write_jsx(manifest: dict[str, Any], output: Path) -> Path:
    output = _output_folder(manifest)
    positions, height_mm = _layout(manifest)
    journal = manifest["journal"]
    width_mm = float(journal.get("artboard_width_mm", journal.get("width_mm", 210)))
    label_offset_x = float(journal.get("label_offset_x_mm", -2))
    label_offset_y = float(journal.get("label_offset_y_mm", -1.5))
    label_font_pt = float(journal.get("label_font_pt", max(7, int(journal.get("minimum_font_pt", 7)))))
    ai_path = _artifact_path(output, f"{manifest['run_id']}.ai")
    pdf_path = _artifact_path(output, f"{manifest['run_id']}.pdf")
    lines = [
        "#target illustrator",
        "(function () {",
        "  var MM = 2.834645669;",
        f"  var doc = app.documents.add(DocumentColorSpace.RGB, {width_mm} * MM, {height_mm} * MM);",
        "  var layerNames = ['08_UNCLASSIFIED_CONTENT','07_NOTES_NONEXPORT','06_SCALE_BARS','05_SCHEMATICS','04_MICROSCOPY','03_STATISTICAL_PLOTS','02_TEXT','01_PANEL_LABELS'];",
        "  var layers = {};",
        "  for (var li = 0; li < layerNames.length; li++) { var ly = doc.layers.add(); ly.name = layerNames[li]; layers[layerNames[li]] = ly; }",
        "  layers['07_NOTES_NONEXPORT'].printable = false; layers['07_NOTES_NONEXPORT'].visible = false;",
    ]
    for panel, box in zip(manifest["panels"], positions):
        src = _jsx_escape(panel["source"])
        label = _label_text(panel["label"], journal.get("label_style", "A"))
        layer = _panel_layer(panel)
        left, top, right, bottom = _validate_normalized_bounds(panel["content_bounds"]["normalized"])
        lines.extend([
            f"  var group = layers['{layer}'].groupItems.add(); var item = group.placedItems.add(); item.file = new File(\"{src}\");",
            f"  var boundL = {left}; var boundT = {top}; var boundR = {right}; var boundB = {bottom};",
            f"  var maxW = {box['w']} * MM; var maxH = {box['h']} * MM; var effectiveW = item.width * (boundR - boundL); var effectiveH = item.height * (boundB - boundT); var scale = Math.min(maxW / effectiveW, maxH / effectiveH) * 100; item.resize(scale, scale);",
            "  effectiveW = item.width * (boundR - boundL); effectiveH = item.height * (boundB - boundT);",
            f"  var contentLeft = {box['x']} * MM + (maxW - effectiveW) / 2; var contentTop = ({height_mm} - {box['y']}) * MM - (maxH - effectiveH) / 2;",
            "  item.position = [contentLeft - boundL * item.width, contentTop + boundT * item.height];",
            "  var clip = group.pathItems.rectangle(contentTop, contentLeft, effectiveW, effectiveH); clip.clipping = true; group.clipped = true;",
            f"  var label = layers['01_PANEL_LABELS'].textFrames.add(); label.contents = \"{label}\"; label.position = [contentLeft + {label_offset_x:g} * MM, contentTop + {abs(label_offset_y):g} * MM]; label.textRange.characterAttributes.size = {label_font_pt:g}; label.textRange.characterAttributes.textFont = app.textFonts.getByName(\"Arial-BoldMT\");",
        ])
    lines.extend([
        f"  var aiFile = new File(\"{_jsx_escape(str(ai_path))}\"); doc.saveAs(aiFile);",
        f"  var pdfFile = new File(\"{_jsx_escape(str(pdf_path))}\"); var pdfOpts = new PDFSaveOptions(); pdfOpts.preserveEditability = true; doc.saveAs(pdfFile, pdfOpts);",
        "  doc.saveAs(aiFile);",
        "})();",
    ])
    jsx = _artifact_path(output, f"{manifest['run_id']}.jsx")
    jsx.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return jsx


def _write_preview(manifest: dict[str, Any], output: Path) -> Path:
    output = _output_folder(manifest)
    positions, height_mm = _layout(manifest)
    journal = manifest["journal"]
    width_mm = float(journal.get("artboard_width_mm", journal.get("width_mm", 210)))
    label_offset_x = float(journal.get("label_offset_x_mm", -2))
    label_offset_y = float(journal.get("label_offset_y_mm", -1.5))
    label_font_pt = float(journal.get("label_font_pt", 8))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_mm}mm" height="{height_mm}mm" viewBox="0 0 {width_mm} {height_mm}">',
        '<rect width="100%" height="100%" fill="white"/>',
    ]
    for panel, box in zip(manifest["panels"], positions):
        source = Path(panel["source"])
        if source.suffix.lower() in RASTER_SUPPORTED:
            try:
                with Image.open(source) as image:
                    rgba = image.convert("RGBA")
                    flattened = Image.new("RGBA", rgba.size, "white")
                    flattened.alpha_composite(rgba)
                    left, top, right, bottom = _validate_normalized_bounds(panel["content_bounds"]["normalized"])
                    crop_box = (
                        round(left * image.width),
                        round(top * image.height),
                        round(right * image.width),
                        round(bottom * image.height),
                    )
                    thumbnail = flattened.convert("RGB").crop(crop_box)
                    thumbnail.thumbnail((800, 800))
                    buffer = io.BytesIO()
                    thumbnail.save(buffer, "PNG", optimize=True)
                encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
                parts.append(
                    f'<image x="{box["x"]}" y="{box["y"]}" width="{box["w"]}" height="{box["h"]}" '
                    f'preserveAspectRatio="xMidYMid meet" href="data:image/png;base64,{encoded}"/>'
                )
            except (UnidentifiedImageError, OSError, ValueError):
                parts.append(
                    f'<text x="{box["x"] + 2}" y="{box["y"] + box["h"] / 2}" font-family="Arial" font-size="2.5">'
                    "Raster preview unavailable</text>"
                )
        else:
            extension = html.escape(source.suffix.lower() or "unknown")
            parts.append(
                f'<text x="{box["x"] + 2}" y="{box["y"] + box["h"] / 2}" font-family="Arial" font-size="2.5">'
                f"Preview unavailable for {extension}</text>"
            )
        label_text = html.escape(_label_text(panel["label"], manifest["journal"].get("label_style", "A")))
        parts.append(
            f'<text x="{box["x"] + label_offset_x}" y="{box["y"] + label_offset_y}" '
            f'font-family="Arial" font-size="{label_font_pt * 0.352778:g}" font-weight="bold">{label_text}</text>'
        )
    parts.append("</svg>")
    preview = _artifact_path(output, "layout_preview.svg")
    preview.write_text("\n".join(parts), encoding="utf-8")
    return preview


def build_captions(manifest_path: str | Path, bilingual: bool = True) -> dict[str, Path]:
    path = Path(manifest_path)
    manifest = load_manifest(path)
    output = _output_folder(manifest)
    output.mkdir(parents=True, exist_ok=True)
    style = manifest["journal"].get("label_style", "A")
    zh_parts, en_parts = [], []
    for panel in manifest.get("panels", []):
        label = _label_text(panel["label"], style)
        facts = panel.get("caption_facts", {})
        zh_parts.append(f"{label} {facts.get('zh') or PLACEHOLDER_ZH}")
        en_parts.append(f"{label} {facts.get('en') or PLACEHOLDER_EN}")
    zh = _artifact_path(output, "caption_zh.md")
    en = _artifact_path(output, "caption_en.md")
    zh.write_text(" ".join(zh_parts) + "\n\n统计与图注信息：样本量、误差线、统计检验、显著性和比例尺如未确认，均须在投稿前补充。\n", encoding="utf-8")
    en.write_text(" ".join(en_parts) + "\n\nStatistics and legend details: confirm sample size, error bars, statistical tests, significance thresholds, and scale bars before submission.\n", encoding="utf-8")
    return {"zh": zh, "en": en} if bilingual else {"en": en}


def _write_traceability(manifest: dict[str, Any], output: Path) -> Path:
    output = _output_folder(manifest)
    path = _artifact_path(output, "traceability.csv")
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["panel", "source", "sha256", "content_guess", "confidence", "content_bounds", "bounds_status"])
        for panel in manifest["panels"]:
            bounds = panel.get("content_bounds") or {}
            writer.writerow([
                panel["label"],
                panel["source"],
                panel["source_fingerprint"]["sha256"],
                panel["content_guess"],
                panel["confidence"],
                json.dumps(bounds.get("normalized"), ensure_ascii=False),
                bounds.get("status"),
            ])
    return path


def run_qa(manifest_path: str | Path) -> Path:
    manifest = load_manifest(manifest_path)
    output = _output_folder(manifest)
    issues = []
    journal = manifest.get("journal", {})
    try:
        layout_boxes, layout_height = _layout(manifest)
    except PharmFigError as exc:
        layout_boxes, layout_height = [], float(journal.get("artboard_height_mm", 297))
        issues.append(f"- 紧凑布局风险：{exc}")
    issues.append(
        "- 标签偏移："
        f"x={float(journal.get('label_offset_x_mm', -2)):g} mm，y={float(journal.get('label_offset_y_mm', -1.5)):g} mm；"
        f"字体={float(journal.get('label_font_pt', 8)):g} pt；验收容差=0.5 mm。"
    )
    issues.append("- 标签布局坐标一致性：SVG 与 JSX 都从同一有效内容左上锚点和偏移生成；坐标差=0.00 mm（≤0.5 mm，非最终字形/PDF实测）。")
    intra_gap = float(journal.get("intra_gap_mm", 1.8))
    inter_gap = float(journal.get("inter_gap_mm", journal.get("gap_mm", 4.5)))
    ratio = inter_gap / intra_gap if intra_gap else float("inf")
    issues.append(f"- 配置gap：intra={intra_gap:g} mm，inter={inter_gap:g} mm，inter/intra={ratio:.3f}；目标范围=2–3，验收容差=0.3 mm。")
    hashes: dict[str, list[str]] = {}
    for panel in manifest.get("panels", []):
        hashes.setdefault(panel["source_fingerprint"]["sha256"], []).append(panel["label"])
        if panel.get("read_error"):
            issues.append(f"- [{panel['label']}] 图片无法完整读取：{panel['read_error']}")
        if panel.get("content_guess") == "待确认":
            issues.append(f"- [{panel['label']}] 图片内容和实验角色待确认")
        bounds = panel.get("content_bounds") or {}
        if bounds.get("status") != "approved":
            issues.append(f"- [{panel['label']}] 内容边界尚未逐面板批准")
        for risk in bounds.get("unresolved_risks") or []:
            issues.append(f"- [{panel['label']}] 内容边界风险：{risk}")
        facts = panel.get("caption_facts", {})
        zh_facts = str(facts.get("zh") or "")
        en_facts = str(facts.get("en") or "")
        missing_zh = not zh_facts.strip() or PLACEHOLDER_ZH in zh_facts
        missing_en = not en_facts.strip() or PLACEHOLDER_EN in en_facts
        if missing_zh:
            issues.append(f"- [{panel['label']}] Chinese caption facts are missing")
        if missing_en:
            issues.append(f"- [{panel['label']}] English caption facts are missing")
        if missing_zh or missing_en:
            issues.append(f"- [{panel['label']}] Bilingual caption facts are incomplete")
        dpi = panel.get("dpi")
        if dpi and dpi < 300:
            issues.append(f"- [{panel['label']}] 栅格图DPI为{dpi}，低于通用300 dpi建议")
        if panel.get("size_basis") == "plot_area":
            plot_area = panel.get("plot_area")
            if not isinstance(plot_area, dict) or plot_area.get("status") != "approved":
                issues.append(f"- [{panel['label']}] plot_area 未批准：不能猜测绘图区尺寸，same-size仅作为风险记录。")
    for digest, labels in hashes.items():
        if len(labels) > 1:
            issues.append(f"- 面板{', '.join(labels)}使用了内容相同的源文件（SHA-256 {digest[:12]}…）")
    if layout_boxes:
        artboard_width = float(journal.get("artboard_width_mm", journal.get("width_mm", 210)))
        horizontal_gaps: list[tuple[float, bool]] = []
        vertical_gaps: list[tuple[float, bool]] = []
        for first in layout_boxes:
            right_neighbors = [second for second in layout_boxes if second is not first and second["x"] >= first["x"] + first["w"] - 1e-6 and min(first["y"] + first["h"], second["y"] + second["h"]) - max(first["y"], second["y"]) > 1e-6]
            if right_neighbors:
                second = min(right_neighbors, key=lambda item: item["x"])
                horizontal_gaps.append((second["x"] - (first["x"] + first["w"]), bool(first.get("group_id") and first.get("group_id") == second.get("group_id"))))
            bottom_neighbors = [second for second in layout_boxes if second is not first and second["y"] >= first["y"] + first["h"] - 1e-6 and min(first["x"] + first["w"], second["x"] + second["w"]) - max(first["x"], second["x"]) > 1e-6]
            if bottom_neighbors:
                second = min(bottom_neighbors, key=lambda item: item["y"])
                vertical_gaps.append((second["y"] - (first["y"] + first["h"]), bool(first.get("group_id") and first.get("group_id") == second.get("group_id"))))
        measured = [(gap, same) for gap, same in horizontal_gaps + vertical_gaps if gap >= 0]
        intra_actual = [gap for gap, same in measured if same]
        inter_actual = [gap for gap, same in measured if not same]
        def _gap_text(values: list[float]) -> str:
            return ", ".join(f"{gap:.2f}" for gap in sorted(values)) or "n/a"
        issues.append(f"- 实际gap（实测gap，共享布局）：水平实测={_gap_text([gap for gap, _ in horizontal_gaps if gap >= 0])} mm；垂直实测={_gap_text([gap for gap, _ in vertical_gaps if gap >= 0])} mm；组内={_gap_text(intra_actual)} mm；组间={_gap_text(inter_actual)} mm。")
        used_area = sum(box["content_w"] * box["content_h"] for box in layout_boxes)
        utilization = used_area / max(1.0, artboard_width * layout_height) * 100
        x_edges = sorted({0.0, artboard_width, *(box["x"] for box in layout_boxes), *(box["x"] + box["w"] for box in layout_boxes)})
        y_edges = sorted({0.0, layout_height, *(box["y"] for box in layout_boxes), *(box["y"] + box["h"] for box in layout_boxes)})
        largest_blank = (0.0, 0.0, 0.0)
        for left_index, left in enumerate(x_edges[:-1]):
            for right in x_edges[left_index + 1:]:
                for top_index, top in enumerate(y_edges[:-1]):
                    for bottom in y_edges[top_index + 1:]:
                        if any(left < box["x"] + box["w"] and right > box["x"] and top < box["y"] + box["h"] and bottom > box["y"] for box in layout_boxes):
                            continue
                        candidate = ((right - left) * (bottom - top), right - left, bottom - top)
                        if candidate[0] > largest_blank[0]:
                            largest_blank = candidate
        issues.append(f"- 画板利用率：{utilization:.1f}%（有效内容面积/画板面积）。")
        issues.append(f"- 连续空白：最大连续空白区域={largest_blank[1]:.1f} × {largest_blank[2]:.1f} mm（{largest_blank[0]:.1f} mm²）；请复核是否应调整span或拆分Figure。")
        groups: dict[str, list[dict[str, Any]]] = {}
        for box in layout_boxes:
            if box["same_size_group"] and (box["same_size_target_width_mm"] is not None or box["same_size_target_height_mm"] is not None):
                groups.setdefault(str(box["same_size_group"]), []).append(box)
        if groups:
            for group, boxes in groups.items():
                target_width = boxes[0]["same_size_target_width_mm"]
                target_height = boxes[0]["same_size_target_height_mm"]
                actual = ", ".join(f"{box['label']}={box['basis_w']:.2f}×{box['basis_h']:.2f}" for box in boxes)
                residual = max(box["same_size_residual_percent"] for box in boxes)
                targets_text = f"宽={target_width:.2f}" if target_width is not None else "宽=未声明"
                targets_text += f"，高={target_height:.2f}" if target_height is not None else "，高=未声明"
                issues.append(f"- same-size（{group}）：{targets_text} mm，实测={actual} mm，残差={residual:.2f}%（有效内容容差=2%；plot_area=3%）。")
        else:
            issues.append("- same-size：未声明可测量的same_size_group目标。")
        low_effective: list[str] = []
        for panel, box in zip(manifest.get("panels", []), layout_boxes):
            pixels = float(panel.get("width_px") or 0) * (float(panel.get("content_bounds", {}).get("normalized", [0, 0, 1, 1])[2]) - float(panel.get("content_bounds", {}).get("normalized", [0, 0, 1, 1])[0]))
            if pixels and box["content_w"]:
                effective_dpi = pixels / (box["content_w"] / 25.4)
                if effective_dpi < 300:
                    low_effective.append(f"{panel.get('label')}={effective_dpi:.0f} dpi")
        issues.append("- 低有效DPI：" + (", ".join(low_effective) if low_effective else "未发现低于300 dpi的可测量栅格面板。"))
        issues.append("- 变形：0.00%（布局以approved effective-content纵横比缩放；验收容差=0%）。")
    protected = [f"{panel.get('label')}：{risk}" for panel in manifest.get("panels", []) for risk in (panel.get("content_bounds") or {}).get("unresolved_risks") or []]
    issues.append("- 保护内容：" + ("；".join(protected) if protected else "未声明额外风险；仍须人工保护坐标轴、图例、统计标记和比例尺。"))
    construction = [str(panel.get("label")) for panel in manifest.get("panels", []) if panel.get("children") or panel.get("construction_path")]
    issues.append("- 构造路径风险：" + (f"面板{', '.join(construction)}含嵌套/构造声明，需人工核对来源映射。" if construction else "未声明嵌套构造路径；现有面板按原始完整源文件和可编辑裁切蒙版放置。"))
    if not issues:
        issues.append("- 未发现自动规则可识别的问题；仍需人工核对科学含义与目标期刊指南。")
    path = _artifact_path(output, "qa_report.md")
    path.write_text("# 投稿前QA报告\n\n" + "\n".join(issues) + "\n", encoding="utf-8")
    return path


def _run_illustrator(jsx: Path) -> tuple[bool, str]:
    if os.name != "nt":
        return False, "自动运行仅支持Windows；请在Illustrator中手动运行JSX。"
    try:
        import win32com.client  # type: ignore
        app = win32com.client.Dispatch("Illustrator.Application")
        app.DoJavaScriptFile(str(jsx))
        return True, "Illustrator已执行JSX。"
    except Exception as exc:  # COM availability differs by Illustrator installation
        return False, f"Illustrator自动调用失败（{type(exc).__name__}）；已保留JSX供手动运行。"


def _archive_stale_illustrator_outputs(manifest: dict[str, Any], output: Path, current_hash: str) -> list[Path]:
    output = _output_folder(manifest)
    stale = [
        _artifact_path(output, f"{manifest['run_id']}.ai"),
        _artifact_path(output, f"{manifest['run_id']}.pdf"),
    ]
    stale = [path for path in stale if path.exists()]
    if not stale:
        return []
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    archive = _artifact_path(output, Path("revisions") / f"{stamp}-{current_hash[:12]}")
    archive.mkdir(parents=True, exist_ok=False)
    archived: list[Path] = []
    for source in stale:
        target = _artifact_path(archive, source.name)
        shutil.move(str(source), str(target))
        archived.append(target)
    return archived


def assemble_manifest(manifest_path: str | Path, run_illustrator: bool = False) -> dict[str, Any]:
    path = Path(manifest_path)
    manifest = load_manifest(path)
    output = _output_folder(manifest)
    _assert_content_bounds_approved(manifest)
    _assert_approved(path, manifest)
    output.mkdir(parents=True, exist_ok=True)
    jsx = _write_jsx(manifest, output)
    preview = _write_preview(manifest, output)
    trace = _write_traceability(manifest, output)
    captions = build_captions(path, bilingual=True)
    qa = run_qa(path)
    current_hash = manifest_hash(manifest)
    archived: list[Path] = []
    ran, message = (False, "Illustrator was not requested.")
    if run_illustrator:
        archived = _archive_stale_illustrator_outputs(manifest, output, current_hash)
        reported_ran, message = _run_illustrator(jsx)
        ai_path = _artifact_path(output, f"{manifest['run_id']}.ai")
        pdf_path = _artifact_path(output, f"{manifest['run_id']}.pdf")
        ran = reported_ran and ai_path.is_file() and pdf_path.is_file()
        if reported_ran and not ran:
            message = f"{message} Current AI/PDF outputs were not both created; attempt recorded as failure."
    status = _artifact_path(output, "illustrator_status.txt")
    status_lines = [
        f"timestamp={_now()}",
        f"manifest_hash={current_hash}",
        f"attempted={str(run_illustrator).lower()}",
        f"success={str(ran).lower()}",
        f"message={message}",
        "archived=" + ",".join(str(item.relative_to(output)) for item in archived),
    ]
    status.write_text("\n".join(status_lines) + "\n", encoding="utf-8")
    return {
        "jsx": jsx,
        "preview": preview,
        "traceability": trace,
        "qa": qa,
        "captions": captions,
        "illustrator_ran": ran,
        "status": status,
        "archived": archived,
    }
