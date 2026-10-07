"""Inspect live Illustrator text before normalizing final-size typography.

The source is never saved. Generated scripts are pending work, not evidence that
Illustrator has inspected or changed a file.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

from PIL import Image, UnidentifiedImageError


DEFAULT_PROFILE = {"body": 8.0, "title": 10.0, "panel": 12.0}


def _positive(value: Any, name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return value


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _classification(audit: dict) -> str:
    live = bool(audit["frames"])
    raster = audit.get("raster_count", 0) + audit.get("placed_count", 0) > 0
    vector = audit.get("path_count", 0) > 0
    if live:
        return "mixed" if raster else "editable_vector"
    if raster:
        return "mixed_without_editable_text" if vector else "raster"
    return "vector_without_editable_text" if vector else "unknown"


def assess_fonts(audit: dict, *, final_width_mm: float,
                 profile: dict | None = None, roles: dict | None = None,
                 tolerance_pt: float = 0.25) -> dict:
    """Calculate targets in final physical units; uncertain roles remain untouched."""
    width = _positive(final_width_mm, "final_width_mm")
    artboard = _positive(audit["artboard_width_pt"], "artboard_width_pt")
    tolerance = _positive(tolerance_pt, "tolerance_pt")
    targets = dict(DEFAULT_PROFILE)
    if profile:
        if set(profile) - set(targets):
            raise ValueError("Profile only supports body, title, panel")
        targets.update(profile)
    targets = {k: _positive(v, k) for k, v in targets.items()}
    roles = roles or {}
    ids = {str(f["id"]) for f in audit["frames"]}
    if len(ids) != len(audit["frames"]) or set(roles) - ids:
        raise ValueError("Duplicate frame IDs or unknown role IDs")
    if set(roles.values()) - {"body", "title", "panel", "keep"}:
        raise ValueError("Roles must be body, title, panel or keep")
    scale = width * 72 / 25.4 / artboard
    base_candidates = []
    for f in audit["frames"]:
        if not f["sizes_pt"] or len(f["sizes_pt"]) != len(f["baseline_shifts_pt"]):
            raise ValueError("Incomplete character sizes/baseline shifts")
        for size, shift in zip(f["sizes_pt"], f["baseline_shifts_pt"]):
            _positive(size, "character size")
            if not math.isfinite(float(shift)):
                raise ValueError("Non-finite baseline shift")
        unshifted = [s for s,b in zip(f['sizes_pt'],f['baseline_shifts_pt']) if abs(b)<.01]
        if len(f['text'].strip()) > 1 and unshifted:
            base_candidates.append(max(unshifted))
    # Each frame gets one vote: a long title must not overwhelm short axis labels.
    base_candidates.sort()
    body_base = base_candidates[(len(base_candidates)-1)//2] if base_candidates else None
    classification = _classification(audit)
    risks = []
    if classification != "editable_vector":
        risks.append("Raster/linked/outlined content cannot be certified as font-normalized.")
    if audit.get("artboard_count", 1) != 1:
        risks.append("Multiple artboards: final-width scale is ambiguous; split before normalization.")
    frames, changes = [], []
    for f in audit["frames"]:
        base_sizes = [s for s, b in zip(f["sizes_pt"], f["baseline_shifts_pt"]) if abs(b) < .01]
        base = max(base_sizes or f["sizes_pt"])
        role = roles.get(str(f["id"]))
        # Size hierarchy and single-letter markers are ambiguous without a role map.
        if role is None:
            role = "review" if (re.fullmatch(r"[A-Z]", f["text"].strip()) or
                                  (body_base and (base > body_base * 1.2 or base < body_base * .8))) else "body"
        if role == "review":
            risks.append(f"Frame {f['id']}: assign body/title/panel/keep before changing it.")
        if role == "keep":
            risks.append(f"Frame {f['id']}: explicit exception retained; not normalized.")
        target = targets.get(role)
        row = {"id": f["id"], "text": f["text"], "role": role,
               "native_base_pt": base, "final_base_pt": base * scale,
               "target_final_pt": target}
        frames.append(row)
        if target and abs(base * scale - target) > tolerance:
            factor = target / (base * scale)
            changes.append({"id": f["id"], "text": f["text"], "factor": factor,
                            "sizes_pt": [s * factor for s in f["sizes_pt"]],
                            "baseline_shifts_pt": [b * factor for b in f["baseline_shifts_pt"]]})
    return {"classification": classification, "status": "manual_review" if risks else
            ("needs_normalization" if changes else "already_consistent"),
            "final_width_mm": width, "placement_scale": scale, "profile": targets,
            "tolerance_pt": tolerance, "frames": frames, "changes": changes,
            "risks": risks, "source_sha256": audit["source_sha256"]}


def _q(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True)


# ES3-compatible JSON writer: Illustrator installations do not all expose JSON.
_JS_COMMON = r'''
function json(v) {
  if(v===null)return 'null';
  if(typeof v==='string')return '"'+v.replace(/\\/g,'\\\\').replace(/"/g,'\\"').replace(/[\x00-\x1f]/g,function(c){var h=c.charCodeAt(0).toString(16);return '\\u'+('0000'+h).slice(-4);})+'"';
  if(typeof v==='number'||typeof v==='boolean')return String(v);
  var a=[],k;if(v instanceof Array){for(k=0;k<v.length;k++)a.push(json(v[k]));return '['+a.join(',')+']';}
  for(k in v)if(v.hasOwnProperty(k))a.push(json(k)+':'+json(v[k]));return '{'+a.join(',')+'}';
}
function write(path, obj){var f=new File(path);f.encoding='UTF-8';if(!f.open('w'))throw Error('Cannot write report');f.write(json(obj));f.close();}
function bounds(t){var b=t.visibleBounds;return [b[0],b[1],b[2],b[3]];}
function capture(doc){
 var rect=doc.artboards[0].artboardRect,frames=[];
 for(var i=0;i<doc.textFrames.length;i++){
  var t=doc.textFrames[i],sz=[],bs=[],fonts=[];
  for(var j=0;j<t.characters.length;j++){
   var a=t.characters[j].characterAttributes;sz.push(a.size);bs.push(a.baselineShift);fonts.push(a.textFont.name);
  }
  if(sz.length)frames.push({id:i,text:t.contents,sizes_pt:sz,baseline_shifts_pt:bs,fonts:fonts,bounds:bounds(t)});
 }
 return {artboard_width_pt:rect[2]-rect[0],artboard_count:doc.artboards.length,
         path_count:doc.pathItems.length,raster_count:doc.rasterItems.length,
         placed_count:doc.placedItems.length,frames:frames};
}
function overlap(a,b){return Math.min(a[2],b[2])-Math.max(a[0],b[0])>0.1 && Math.min(a[1],b[1])-Math.max(a[3],b[3])>0.1;}
var doc=null,oldUI=app.userInteractionLevel;
try {
 for(var di=0;di<app.documents.length;di++){
  try{if(app.documents[di].fullName.fsName===new File(source).fsName)throw Error('SOURCE_ALREADY_OPEN');}
  catch(e){if(String(e).indexOf('SOURCE_ALREADY_OPEN')>=0)throw e;}
 }
 app.userInteractionLevel=UserInteractionLevel.DONTDISPLAYALERTS;
 doc=app.open(new File(source));
'''

_JS_FINALLY = r'''
} finally {
 if(doc)doc.close(SaveOptions.DONOTSAVECHANGES); // DoNotSaveChanges: source remains untouched
 app.userInteractionLevel=oldUI;
}
})();
'''


def _output(folder: str | Path, names: list[str]) -> Path:
    folder = Path(folder).resolve()
    if any((folder / name).exists() for name in names):
        raise ValueError("Output already exists; use a new review directory")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _run(script: Path) -> None:
    from .workflow import _run_illustrator
    ok, message = _run_illustrator(script)
    if not ok:
        raise ValueError(f"Illustrator did not complete: {message}")


def inspect_fonts(source: str | Path, output: str | Path, *, final_width_mm: float,
                  run_illustrator: bool = False) -> dict:
    width = _positive(final_width_mm, "final_width_mm")
    source = Path(source).resolve(strict=True)
    folder = _output(output, ["font-audit.json", "font-inspect.jsx", "font-report.json"])
    digest = _hash(source)
    # Pillow decodes the bytes, so a raster named .svg is still a raster.
    raster = False
    try:
        with Image.open(source) as im:
            raster = im.format in {"PNG", "JPEG", "TIFF", "BMP", "GIF", "WEBP"}
            if raster:
                im.verify()
    except UnidentifiedImageError:
        pass
    if raster:
        report = folder / "font-report.json"
        report.write_text(json.dumps({"classification": "raster", "status": "manual_review",
            "source": str(source), "source_sha256": digest,
            "risks": ["No editable fonts in raster pixels; obtain the vector source."]}, indent=2), encoding="utf-8")
        return {"status": "manual_review", "report": report}
    if source.suffix.lower() not in {".ai", ".pdf", ".svg", ".eps"}:
        raise ValueError("Supported vector containers: AI, PDF, SVG, EPS; extension alone is not proof of vectors")
    if source.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("PDF inspection requires pip install '.[vector]' for page-count validation") from exc
        if len(PdfReader(source).pages) != 1:
            raise ValueError("Use a single-page PDF; Illustrator imports only one page")
    audit_path, script = folder / "font-audit.json", folder / "font-inspect.jsx"
    payload = "var result=capture(doc);result.source=source;result.source_sha256=" + _q(digest) + ";\n"
    payload += "write(" + _q(str(audit_path)) + ",result);\n"
    script.write_text("#target illustrator\n(function(){\nvar source=" + _q(str(source)) + ";\n" +
                      _JS_COMMON + payload + _JS_FINALLY, encoding="utf-8")
    result = {"status": "inspection_pending", "jsx": script, "audit": audit_path}
    if run_illustrator:
        _run(script)
        if not audit_path.exists() or _hash(source) != digest:
            raise ValueError("Inspection did not return an audit or source changed")
        report = assess_fonts(json.loads(audit_path.read_text(encoding="utf-8-sig")), final_width_mm=width)
        report_path = folder / "font-report.json"
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        result.update(status=report["status"], report=report_path)
    return result


def normalize_fonts(audit_path: str | Path, output: str | Path, *, final_width_mm: float,
                    profile: dict | None = None, roles: dict | None = None,
                    run_illustrator: bool = False) -> dict:
    audit = json.loads(Path(audit_path).read_text(encoding="utf-8-sig"))
    source = Path(audit["source"]).resolve(strict=True)
    if _hash(source) != audit["source_sha256"]:
        raise ValueError("Source changed since inspection; run fonts-inspect again")
    if audit.get("artboard_count", 1) != 1:
        raise ValueError("Split multiple artboards before normalizing")
    report = assess_fonts(audit, final_width_mm=final_width_mm, profile=profile, roles=roles)
    folder = _output(output, ["font-plan.json", "font-normalize.jsx", "normalized.ai", "normalized.pdf", "font-after.json"])
    plan = folder / "font-plan.json"
    plan.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if not report["changes"]:
        return {"status": report["status"], "report": plan}
    script, ai, pdf, after = [folder / f for f in ("font-normalize.jsx", "normalized.ai", "normalized.pdf", "font-after.json")]
    payload = "var expected=" + _q(audit["frames"]) + ";var changes=" + _q(report["changes"]) + ";\n"
    payload += r'''
var before=capture(doc);
if(before.frames.length!==expected.length)throw Error('Text frame count changed');
for(var i=0;i<expected.length;i++){
 var e=expected[i],t=doc.textFrames[e.id];
 if(t.contents!==e.text || t.characters.length!==e.sizes_pt.length)throw Error('Text identity changed');
 for(var j=0;j<t.characters.length;j++)if(Math.abs(t.characters[j].characterAttributes.size-e.sizes_pt[j])>0.01)throw Error('Text style changed since audit');
}
for(var i=0;i<changes.length;i++){
 var ch=changes[i],t=doc.textFrames[ch.id];
 for(var j=0;j<t.characters.length;j++){
  t.characters[j].characterAttributes.size=ch.sizes_pt[j];
  t.characters[j].characterAttributes.baselineShift=ch.baseline_shifts_pt[j];
 }
}
app.redraw();var result=capture(doc);result.new_text_overlaps=[];result.outside_artboard=[];
var ar=doc.artboards[0].artboardRect;
for(var i=0;i<result.frames.length;i++){
 var b=result.frames[i].bounds;
 if(b[0]<ar[0]||b[1]>ar[1]||b[2]>ar[2]||b[3]<ar[3])result.outside_artboard.push(result.frames[i].id);
 for(var j=i+1;j<result.frames.length;j++){
  if(overlap(b,result.frames[j].bounds)&&!overlap(before.frames[i].bounds,before.frames[j].bounds))result.new_text_overlaps.push([result.frames[i].id,result.frames[j].id]);
 }
}
'''
    payload += "var ai=new File(" + _q(str(ai)) + ");var pdf=new File(" + _q(str(pdf)) + ");\n"
    payload += "if(ai.exists||pdf.exists)throw Error('Derivative already exists');\n"
    payload += "var ao=new IllustratorSaveOptions();ao.pdfCompatible=true;doc.saveAs(ai,ao);\n"
    payload += "var po=new PDFSaveOptions();po.preserveEditability=true;doc.saveAs(pdf,po);\n"
    payload += "write(" + _q(str(after)) + ",result);\n"
    script.write_text("#target illustrator\n(function(){\nvar source=" + _q(str(source)) + ";\n" +
                      _JS_COMMON + payload + _JS_FINALLY, encoding="utf-8")
    result = {"status": "normalization_pending", "report": plan, "jsx": script, "ai": ai, "pdf": pdf, "after": after}
    if run_illustrator:
        _run(script)
        if _hash(source) != audit["source_sha256"] or not all(p.exists() for p in (ai,pdf,after)):
            raise ValueError("Missing derivative/audit or source changed; normalization not verified")
        actual = json.loads(after.read_text(encoding="utf-8-sig"))
        by_id = {f["id"]: f for f in actual["frames"]}
        for frame in audit["frames"]:
            if by_id[frame["id"]]["text"] != frame["text"]:
                raise ValueError("Text content changed")
            if frame.get('fonts') != by_id[frame['id']].get('fonts'):
                raise ValueError("Font family/style changed")
        for change in report["changes"]:
            observed = by_id[change["id"]]
            for field in ("sizes_pt", "baseline_shifts_pt"):
                if len(observed[field]) != len(change[field]) or any(abs(a-b)>.02 for a,b in zip(observed[field],change[field])):
                    raise ValueError("Exported character styles differ from plan")
        result["status"] = "derivative_created_requires_visual_review"
    return result
