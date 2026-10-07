import copy
import hashlib
import json

import pytest

from pharmfig.typography import assess_fonts, inspect_fonts, normalize_fonts


def audit(tmp_path, *, paths=2, rasters=0, frames=None):
    source = tmp_path / 'source.svg'
    source.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    return {
        'source': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'artboard_width_pt': 200, 'path_count': paths, 'raster_count': rasters,
        'placed_count': 0, 'frames': frames if frames is not None else [
            {'id': 0, 'text': 'Time (h)', 'sizes_pt': [16] * 8, 'baseline_shifts_pt': [0] * 8},
        ],
    }


def test_final_size_controls_need_not_native_size(tmp_path):
    data = audit(tmp_path)
    result = assess_fonts(data, final_width_mm=100 * 25.4 / 72)
    assert result['classification'] == 'editable_vector'
    assert result['status'] == 'already_consistent'
    assert result['frames'][0]['final_base_pt'] == pytest.approx(8)
    assert not result['changes']


def test_scale_plan_preserves_superscript_size_and_shift(tmp_path):
    data = audit(tmp_path, frames=[{'id': 0, 'text': 'x2', 'sizes_pt': [10, 6],
                                  'baseline_shifts_pt': [0, 3]}])
    original = copy.deepcopy(data)
    result = assess_fonts(data, final_width_mm=200 * 25.4 / 72)
    assert result['changes'][0]['factor'] == pytest.approx(.8)
    assert result['changes'][0]['sizes_pt'] == pytest.approx([8, 4.8])
    assert result['changes'][0]['baseline_shifts_pt'] == pytest.approx([0, 2.4])
    assert data == original


@pytest.mark.parametrize('paths,rasters,kind', [(0,1,'raster'),(3,0,'vector_without_editable_text'),(3,1,'mixed_without_editable_text')])
def test_noneditable_sources_never_claim_normalized(tmp_path, paths, rasters, kind):
    result = assess_fonts(audit(tmp_path, paths=paths, rasters=rasters, frames=[]), final_width_mm=60)
    assert result['classification'] == kind
    assert result['status'] == 'manual_review'
    assert not result['changes']


def test_mixed_report_is_partial_even_if_live_text_matches(tmp_path):
    result = assess_fonts(audit(tmp_path, rasters=1), final_width_mm=100*25.4/72)
    assert result['classification'] == 'mixed'
    assert result['status'] == 'manual_review'


def test_roles_keep_panel_title_body_hierarchy(tmp_path):
    data = audit(tmp_path, frames=[
        {'id': 0, 'text': 'A', 'sizes_pt': [14], 'baseline_shifts_pt': [0]},
        {'id': 1, 'text': 'Title', 'sizes_pt': [14]*5, 'baseline_shifts_pt': [0]*5},
        {'id': 2, 'text': 'Time', 'sizes_pt': [9]*4, 'baseline_shifts_pt': [0]*4},
    ])
    result = assess_fonts(data, final_width_mm=200*25.4/72, roles={'0':'panel','1':'title'})
    assert [f['target_final_pt'] for f in result['frames']] == [12,10,8]


def test_ambiguous_large_text_is_not_flattened(tmp_path):
    data = audit(tmp_path, frames=[
        {'id': 0, 'text': 'A', 'sizes_pt': [16], 'baseline_shifts_pt': [0]},
        {'id': 1, 'text': 'Axis label', 'sizes_pt': [8]*10, 'baseline_shifts_pt': [0]*10},
    ])
    result = assess_fonts(data, final_width_mm=200*25.4/72)
    assert result['status'] == 'manual_review'
    assert not result['changes']
    assert result['frames'][0]['role'] == 'review'


def test_long_title_does_not_outvote_short_axis_or_detached_superscript(tmp_path):
    data = audit(tmp_path, frames=[
        {'id':0,'text':'Long descriptive chart title','sizes_pt':[20]*28,'baseline_shifts_pt':[0]*28},
        {'id':1,'text':'Time (h)','sizes_pt':[16]*8,'baseline_shifts_pt':[0]*8},
        {'id':2,'text':'2','sizes_pt':[9],'baseline_shifts_pt':[0]},
    ])
    result=assess_fonts(data,final_width_mm=200*25.4/72)
    assert [f['role'] for f in result['frames']]==['review','body','review']
    assert [c['id'] for c in result['changes']]==[1]


@pytest.mark.parametrize('width', [0,-1,float('nan'),float('inf')])
def test_rejects_invalid_physical_size(tmp_path, width):
    with pytest.raises(ValueError):
        assess_fonts(audit(tmp_path), final_width_mm=width)


def test_raster_detection_uses_pixels_not_extension(tmp_path):
    from PIL import Image
    source = tmp_path/'pretend.svg'
    Image.new('RGB',(20,20)).save(source,format='PNG')
    result = inspect_fonts(source,tmp_path/'report',final_width_mm=50)
    report = json.loads(result['report'].read_text())
    assert report['classification'] == 'raster'
    assert not list((tmp_path/'report').glob('*.jsx'))


def test_eps_header_is_not_proof_of_raster_content(tmp_path):
    from PIL import Image
    source=tmp_path/'sample.eps'
    Image.new('RGB',(20,20)).save(source,format='EPS')
    result=inspect_fonts(source,tmp_path/'report',final_width_mm=50)
    assert result['status']=='inspection_pending'


def test_inspection_not_executed_is_pending(tmp_path):
    data = audit(tmp_path)
    result = inspect_fonts(data['source'],tmp_path/'report',final_width_mm=50)
    assert result['status'] == 'inspection_pending'
    assert 'DoNotSaveChanges' in result['jsx'].read_text()
    assert not result['audit'].exists()


def test_stale_audit_is_rejected(tmp_path):
    data = audit(tmp_path)
    path=tmp_path/'audit.json';path.write_text(json.dumps(data))
    from pathlib import Path
    Path(data['source']).write_text('changed')
    with pytest.raises(ValueError,match='changed'):
        normalize_fonts(path,tmp_path/'new',final_width_mm=60)


def test_normalize_is_derivative_and_does_not_fake_success(tmp_path):
    data=audit(tmp_path);path=tmp_path/'audit.json';path.write_text(json.dumps(data))
    result=normalize_fonts(path,tmp_path/'new',final_width_mm=200*25.4/72)
    assert result['status']=='normalization_pending'
    assert not result['ai'].exists()
    script=result['jsx'].read_text()
    assert 'baselineShift' in script and 'overlap' in script
    assert 'DONTDISPLAYALERTS' in script


def test_cli_registers_typography_commands():
    from pharmfig.cli import parser
    args=parser().parse_args(['fonts-inspect','a.pdf','--output','b','--final-width-mm','80'])
    assert args.command=='fonts-inspect'
