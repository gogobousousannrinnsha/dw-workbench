import importlib.util
import json
from pathlib import Path
import sys
import os
import tempfile
import uuid
import shutil
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'packages/docuworks-integrations'))
sys.path.insert(0, str(ROOT/'packages/docuworks-integrations/tests'))
from test_review_report import sample


@pytest.fixture
def tmp_path():
    # Keep bundle descendants below native Windows rename path limits.
    root = Path(os.environ.get('DOCUWORKS_INTEGRATIONS_TEST_TMP', str(Path(tempfile.gettempdir())/'dw-ocr')))/uuid.uuid4().hex
    root.mkdir(parents=True)
    yield root
    shutil.rmtree(root, ignore_errors=True)


def entry():
    spec = importlib.util.spec_from_file_location('review_report_entry', ROOT/'portable/scripts/review_report.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('mode', ['folder', 'manifest', 'dialog', 'cancel', 'interrupt', 'invalid'])
def test_portable_report_flow(tmp_path, monkeypatch, mode):
    saved = sample(tmp_path)
    module = entry()
    def choose(initial):
        if mode == 'interrupt':
            raise KeyboardInterrupt()
        return '' if mode == 'cancel' else str(saved.root)
    monkeypatch.setattr(module, 'choose_directory', choose)
    args = [] if mode in ('dialog', 'cancel', 'interrupt') else [str(
        saved.root/'manifest.json' if mode == 'manifest' else tmp_path if mode == 'invalid' else saved.root)]
    code = module.run(args)
    assert code == (130 if mode == 'interrupt' else 1 if mode == 'invalid' else 0)
    outputs = list(tmp_path.glob('*_確認一覧_*.json'))
    if mode in ('cancel', 'interrupt', 'invalid'):
        assert outputs == []
    else:
        assert len(outputs) == 1
        assert json.loads(outputs[0].read_text(encoding='utf-8'))['summary']['flagged_regions'] == 2
        assert module.run(args) == 0
        assert len(list(tmp_path.glob('*_確認一覧_*.json'))) == 2


def test_layout_includes_both_report_files():
    layout = json.loads((ROOT/'portable/layout.json').read_text(encoding='utf-8'))
    assert {'OCR確認一覧.bat', 'scripts/review_report.py'} <= set(layout['files'])
