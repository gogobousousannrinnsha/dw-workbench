"""The source BAT is an old template: never retain its old version pins."""
from pathlib import Path
import importlib.util
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from prepare_review_ab import repair_launcher


def test_old_template_and_repeated_preparation_keep_candidate_pins():
    source=Path(__file__).resolve().parents[2]/'portable/repair_project_wheels.bat'
    patched=repair_launcher(source.read_bytes())
    assert b'docuworks-ctypes==1.0.1' in patched
    assert b'docuworks-integrations==0.12.0+reviewab.1' in patched
    assert b'docuworks-integrations==0.7.0' not in patched
    assert repair_launcher(patched)==patched


def test_compare_detects_ocr_and_environment_changes():
    script = Path(__file__).resolve().parents[2]/'portable/scripts/compare_ab.py'
    spec = importlib.util.spec_from_file_location('compare_ab_test', script)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    base = dict(status='COMPLETE', settings={}, fingerprints={'models':'same'}, python='same',
                documents=[dict(source_sha256='same', content_geometry_sha256='same')],
                elapsed_seconds=1, events=[])
    assert module.compare(dict(base, variant='A'), dict(base, variant='B'))['comparable']
    altered = dict(base, variant='B', fingerprints={},
                   documents=[dict(source_sha256='same', content_geometry_sha256='different')])
    result = module.compare(dict(base, variant='A'), altered)
    assert not result['comparable']
    assert any('OCR結果' in s for s in result['issues'])
