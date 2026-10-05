from dataclasses import replace
import json
import math
from pathlib import Path
import subprocess
import sys
import pytest
from test_canonical_results import fixture_result
from docuworks_integrations.results import save_ocr_result, sha256, load_ocr_result
from docuworks_integrations.review_report import build_review_report, export_review_report


def sample(root):
    result, assets = fixture_result(root, two=True)
    first, second = result.pages
    base = first.regions[0]
    regions = tuple(replace(base, id=f'p0001-r{i:06d}', confidence=score)
        for i, score in enumerate((0.79, 0.8, None, 0.99), 1))
    result = replace(result, schema_version='1.1', source=result.source | {'page_count': 3}, pages=(
        replace(first, regions=regions, recognition_status='TEXT_DETECTED'),
        replace(second, regions=(), recognition_status='NO_TEXT_DETECTED')))
    return save_ocr_result(result, root/'run', assets=assets)


def test_priorities_boundary_identity_coordinates_and_no_text(tmp_path):
    saved = sample(tmp_path)
    before = {p.relative_to(saved.root): sha256(p) for p in saved.root.rglob('*') if p.is_file()}
    report = build_review_report(saved)
    assert report['summary'] == dict(processed_pages=2, regions=4, flagged_regions=2,
        low_confidence=1, confidence_unknown=1, no_text_pages=[2], unprocessed_pages=[3])
    assert [r['region_id'] for r in report['regions']] == ['p0001-r000001', 'p0001-r000003']
    assert report['regions'][0]['bbox_mm'] == saved.pages[0].regions[0].bbox_mm
    assert report['regions'][0]['text'] == ' テスト '
    assert report['run_id'] == saved.run_id and report['manifest_sha256'] == saved.manifest_sha256
    output = export_review_report(saved, tmp_path/'確認 一覧.json')
    assert json.loads(output.read_text(encoding='utf-8'))['summary'] == report['summary']
    assert before == {p.relative_to(saved.root): sha256(p) for p in saved.root.rglob('*') if p.is_file()}
    assert not list(tmp_path.glob('.review-report-*'))


@pytest.mark.parametrize('threshold', [-0.1, 1.1, math.nan, math.inf, True, '0.8'])
def test_invalid_threshold_does_not_create_output(tmp_path, threshold):
    saved = sample(tmp_path)
    output = tmp_path/'report.json'
    with pytest.raises(ValueError):
        export_review_report(saved, output, threshold=threshold)
    assert not output.exists()


def test_existing_bundle_and_changed_inputs_are_preserved(tmp_path):
    saved = sample(tmp_path)
    output = tmp_path/'report.json'
    output.write_text('existing', encoding='utf-8')
    with pytest.raises(FileExistsError):
        export_review_report(saved, output)
    assert output.read_text() == 'existing'
    with pytest.raises(ValueError):
        export_review_report(saved, saved.root/'report.json')
    (saved.root/saved.pages[0].image).write_bytes(b'corrupt')
    with pytest.raises(RuntimeError):
        export_review_report(saved, tmp_path/'bad.json')
    assert not (tmp_path/'bad.json').exists()


def test_publish_failure_or_cancel_leaves_no_partial_report(tmp_path, monkeypatch):
    import docuworks_integrations.review_report as module
    saved = sample(tmp_path)
    def fail(*args):
        raise KeyboardInterrupt()
    monkeypatch.setattr(module, 'publish_new', fail)
    with pytest.raises(KeyboardInterrupt):
        export_review_report(saved, tmp_path/'cancel.json')
    assert not (tmp_path/'cancel.json').exists()
    assert not list(tmp_path.glob('.review-report-*'))
    assert load_ocr_result(saved.root).manifest_sha256 == saved.manifest_sha256


def test_cli_without_optional_dependencies(tmp_path):
    from docuworks_integrations.cli import main
    saved = sample(tmp_path)
    output = tmp_path/'cli.json'
    assert main(['review-report', '--run-dir', str(saved.root), '--output', str(output), '--threshold', '1']) == 0
    assert json.loads(output.read_text(encoding='utf-8'))['summary']['flagged_regions'] == 4
    with pytest.raises(SystemExit) as error:
        main(['review-report', '--run-dir', str(saved.root), '--output', str(output)])
    assert error.value.code == 2


def test_standard_library_only_and_no_priority_for_high_scores(tmp_path):
    result, assets = fixture_result(tmp_path)
    saved = save_ocr_result(result, tmp_path/'run', assets=assets)
    report = build_review_report(saved)
    assert report['regions'] == [] and report['summary']['no_text_pages'] == []
    code = '''import sys
sys.path.insert(0, sys.argv[1])
from docuworks_integrations import load_ocr_result, export_review_report
export_review_report(load_ocr_result(sys.argv[2]), sys.argv[3])
assert not any(n.split('.')[0] in ('PIL','numpy','cv2','paddle','paddleocr','docuworks_ctypes') for n in sys.modules)
'''
    package = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, '-S', '-B', '-X', 'utf8', '-c', code, str(package), str(saved.root),
        str(tmp_path/'stdlib.json')], check=True)
