"""Exercise the Portable entry against real validation/extraction with synthetic inputs."""
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'packages/docuworks-integrations'))
sys.path.insert(0, str(ROOT / 'packages/docuworks-integrations/tests'))
from docuworks_integrations import load_structured_result, reviewed as r, templates as t
from test_reviewed import hashes, write
from test_structured import inputs


def entry(tmp_path):
    spec = importlib.util.spec_from_file_location('apply_entry', ROOT / 'portable/scripts/apply_template.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / '別の場所 日本語 Portable'
    root.mkdir()
    module.__file__ = str(root / 'scripts/apply_template.py')
    return module, root


@pytest.mark.parametrize('mode', ['ok', 'needs_review', 'not_applicable'])
def test_dialog_flow_real_extraction_and_status(tmp_path, monkeypatch, capsys, mode):
    template, reviewed, run, session = inputs(tmp_path, monkeypatch)
    data = template.data
    if mode == 'needs_review':
        data['pages'][0]['rectangles'][0]['y'] = 6
    if mode == 'not_applicable':
        data['pages'][0]['width_mm'] += 1
    write(template.root / 'template.json', data)
    r._write_manifest(template.root, t.SCHEMA, t.FILES)
    original = [hashes(p) for p in (template.root, reviewed.root, run.root, session.root)]
    module, app = entry(tmp_path)
    answers = iter([str(reviewed.root), str(template.root)])
    monkeypatch.setattr(module, 'choose_directory', lambda *args: next(answers))
    monkeypatch.chdir(tmp_path)
    assert module.run([]) == (0 if mode == 'ok' else 2)
    saved = list((app / 'structured').glob('result-*'))
    assert len(saved) == 1
    result = load_structured_result(saved[0])
    assert result.data['status'] == mode
    if mode == 'ok':
        assert result.data['fields'][0]['value'] == '80℃'
    assert [hashes(p) for p in (template.root, reviewed.root, run.root, session.root)] == original
    assert str(saved[0] / 'structured.json') in capsys.readouterr().out
    assert not (tmp_path / 'structured').exists()


def test_folder_or_json_inputs_and_repeated_runs_keep_previous_results(tmp_path, monkeypatch):
    template, reviewed, *_ = inputs(tmp_path, monkeypatch)
    module, app = entry(tmp_path)
    monkeypatch.setattr(module, 'choose_directory', lambda *args: pytest.fail('unexpected dialog'))
    assert module.run([str(reviewed.root), str(template.root)]) == 0
    before = hashes(app / 'structured')
    assert module.run([str(reviewed.root / 'reviewed.json'), str(template.root / 'template.json')]) == 0
    after = hashes(app / 'structured')
    assert all(after[k] == v for k, v in before.items())
    assert len(list((app / 'structured').glob('result-*'))) == 2


@pytest.mark.parametrize('cancel_step', [1, 2])
def test_cancel_creates_no_result(tmp_path, monkeypatch, cancel_step):
    template, reviewed, *_ = inputs(tmp_path, monkeypatch)
    module, app = entry(tmp_path)
    answers = iter([''] if cancel_step == 1 else [str(reviewed.root), ''])
    monkeypatch.setattr(module, 'choose_directory', lambda *args: next(answers))
    assert module.run([]) == 0
    assert not (app / 'structured').exists()


@pytest.mark.parametrize('kind', ['wrong-folder', 'corrupt-template', 'corrupt-reviewed'])
def test_invalid_inputs_do_not_publish_results(tmp_path, monkeypatch, kind):
    template, reviewed, *_ = inputs(tmp_path, monkeypatch)
    if kind == 'corrupt-template':
        (template.root / 'template.json').write_text('{}')
    if kind == 'corrupt-reviewed':
        (reviewed.root / 'reviewed.json').write_text('{}')
    module, app = entry(tmp_path)
    assert module.run([str(tmp_path if kind == 'wrong-folder' else reviewed.root), str(template.root)]) == 1
    assert not list((app / 'structured').glob('result-*'))
