from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .workflow import (
    ApprovalError,
    PharmFigError,
    analyze_cloud_panels,
    approve_content_bounds,
    approve_manifest,
    assemble_manifest,
    build_captions,
    detect_content_bounds,
    load_manifest,
    propose_manifest,
    run_qa,
    scan_folder,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="pharmfig", description="Approval-gated scientific figure assembly")
    commands = root.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan", help="Read-only scan of a figure folder")
    scan.add_argument("folder")
    scan.add_argument("--run-id", required=True)

    propose = commands.add_parser("propose", help="Explain panel logic before assembly")
    propose.add_argument("manifest")
    propose.add_argument("--journal")

    approve = commands.add_parser("approve", help="Explicitly approve the current manifest")
    approve.add_argument("manifest")

    bounds = commands.add_parser("bounds", help="Detect candidate visible-content bounds and write a manual review sheet")
    bounds.add_argument("manifest")

    bounds_approve = commands.add_parser("bounds-approve", help="Approve every current panel content bound")
    bounds_approve.add_argument("manifest")

    assemble = commands.add_parser("assemble", help="Generate JSX; requires valid approval")
    assemble.add_argument("manifest")
    assemble.add_argument("--run-illustrator", action="store_true")

    caption = commands.add_parser("caption", help="Generate captions from confirmed facts only")
    caption.add_argument("manifest")
    caption.add_argument("--bilingual", action="store_true")

    qa = commands.add_parser("qa", help="Generate a pre-submission QA report")
    qa.add_argument("manifest")

    vision = commands.add_parser("vision", help="Optional per-panel cloud vision after explicit consent")
    vision.add_argument("manifest")
    vision.add_argument("--panels", required=True, help="Comma-separated approved panel labels")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "scan":
            run = PROJECT_ROOT / "runs" / args.run_id
            result = scan_folder(args.folder, run, args.run_id)
            print(result)
        elif args.command == "propose":
            print(propose_manifest(args.manifest, args.journal))
        elif args.command == "approve":
            manifest = load_manifest(args.manifest)
            print(f"即将批准面板顺序：{', '.join(panel.get('label', '?') for panel in manifest.get('panels', []))}")
            typed = input("确认科学逻辑和面板顺序后，输入 APPROVE：").strip()
            if typed != "APPROVE":
                raise ApprovalError("未收到明确批准，manifest保持草稿状态。")
            approve_manifest(args.manifest)
            print("已批准。任何面板、事实、设置或源文件变化都会自动撤销批准。")
        elif args.command == "bounds":
            outputs = detect_content_bounds(args.manifest)
            for key, value in outputs.items():
                print(f"{key}: {value}")
            print("候选内容框仅供审阅；逐面板确认前不得组图。")
        elif args.command == "bounds-approve":
            manifest = load_manifest(args.manifest)
            for panel in manifest.get("panels", []):
                bounds = panel.get("content_bounds") or {}
                print(f"{str(panel.get('label') or panel.get('id')).upper()}: {bounds.get('normalized')} risks={bounds.get('unresolved_risks') or []}")
            typed = input("逐面板核对内容框后，输入 APPROVE_BOUNDS：").strip()
            if typed != "APPROVE_BOUNDS":
                raise ApprovalError("未收到内容框批准；所有内容框保持草稿状态。")
            approve_content_bounds(args.manifest)
            print("内容框已批准；科学逻辑批准已撤销，请重新运行 pharmfig approve。")
        elif args.command == "assemble":
            outputs = assemble_manifest(args.manifest, args.run_illustrator)
            for key, value in outputs.items():
                print(f"{key}: {value}")
        elif args.command == "caption":
            print(build_captions(args.manifest, args.bilingual))
        elif args.command == "qa":
            print(run_qa(args.manifest))
        elif args.command == "vision":
            labels = [label.strip() for label in args.panels.split(",") if label.strip()]
            reviewed = input(
                "The resized previews retain visible pixels/text and receive no OCR redaction. "
                "After reviewing them as safe to transport, enter REVIEWED_SAFE: "
            ).strip()
            if reviewed != "REVIEWED_SAFE":
                raise ApprovalError("Visible text/content safety was not acknowledged; no cloud service was called.")
            typed = input(f"将仅上传面板 {', '.join(labels)} 的去文件名缩放预览。输入 UPLOAD 确认：").strip()
            if typed != "UPLOAD":
                raise ApprovalError("未收到逐次上传确认；未调用任何云端服务。")
            print(
                analyze_cloud_panels(
                    args.manifest,
                    labels,
                    confirm_upload=True,
                    confirm_content_safe=True,
                )
            )
        return 0
    except (PharmFigError, ApprovalError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
