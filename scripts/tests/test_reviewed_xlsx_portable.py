"""Folder selection boundary and real export, with only dialogs substituted."""
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'packages/docuworks-integrations'))
sys.path.insert(0, str(ROOT / 'packages/docuworks-integrations/tests'))
from test_reviewed_xlsx import fixture, read_rows


def entry():
    spec = importlib.util.spec_from_file_location('xlsx_entry', ROOT / 'portable/scripts/export_reviewed_xlsx.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('mode', ['dialog', 'folder', 'json', 'cancel', 'wrong', 'interrupt'])
def test_export_flow(tmp_path, monkeypatch, mode):
    result = fixture(tmp_path, monkeypatch, ['00123', '=1+2'])
    module = entry()
    def choose(initial):
        assert initial.name in ('portable', 'OUTPUT')
        if mode == 'interrupt': raise KeyboardInterrupt()
        return '' if mode == 'cancel' else str(result.root)
    monkeypatch.setattr(module, 'choose_directory', choose)
    args = [] if mode in ('dialog', 'cancel', 'interrupt') else [str(
        result.root / 'reviewed.json' if mode == 'json' else tmp_path if mode == 'wrong' else result.root)]
    code = module.run(args)
    assert code == (130 if mode == 'interrupt' else 1 if mode == 'wrong' else 0)
    files = list(tmp_path.glob('*_全文_*.xlsx'))
    if mode in ('cancel', 'wrong', 'interrupt'):
        assert not files
    else:
        assert len(files) == 1 and [row[2] for row in read_rows(files[0])['全文一覧'][1:]] == ['00123', '=1+2']
        assert module.run(args) == 0
        assert len(list(tmp_path.glob('*_全文_*.xlsx'))) == 2


def test_picker_options_and_cleanup(monkeypatch):
    import tkinter
    from tkinter import filedialog
    calls = []
    class Window:
        def withdraw(self): calls.append('withdraw')
        def attributes(self, *args): calls.append(args)
        def destroy(self): calls.append('destroy')
    monkeypatch.setattr(tkinter, 'Tk', Window)
    def dialog(**kwargs):
        assert kwargs['mustexist'] and 'reviewed.json' in kwargs['title']
        return 'selected'
    monkeypatch.setattr(filedialog, 'askdirectory', dialog)
    assert entry().choose_directory(Path('INPUT')) == 'selected'
    assert calls[-1] == 'destroy'


def test_offline_repair_pins_and_idempotence():
    sys.path.insert(0, str(ROOT / 'scripts'))
    from prepare_reviewed_xlsx import repair_launcher
    source = (ROOT / 'portable/repair_project_wheels.bat').read_bytes()
    patched = repair_launcher(source, '0.12.0+reviewxlsx.1')
    assert b'docuworks-ctypes==1.0.1' in patched
    assert b'docuworks-integrations==0.12.0+reviewxlsx.1 XlsxWriter==3.2.9' in patched
    assert patched == repair_launcher(patched, '0.12.0+reviewxlsx.1')


def test_wheel_script_relocation_and_shebang(tmp_path):
    sys.path.insert(0, str(ROOT / 'scripts'))
    from prepare_reviewed_xlsx import installed_member_matches
    folder = tmp_path / 'runtime/Scripts'
    folder.mkdir(parents=True)
    script = folder / 'helper.py'
    script.write_bytes(b'#!local-python\nprint(123)\n')
    member = 'example-1.0.data/scripts/helper.py'
    assert installed_member_matches(tmp_path, member, b'#!python\nprint(123)\n')
    assert not installed_member_matches(tmp_path, member, b'#!python\nprint(456)\n')
