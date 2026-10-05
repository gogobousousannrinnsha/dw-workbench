"""Real validated bundles and an independent Excel reader; no native DLL."""
import copy
from pathlib import Path
import re
import subprocess
import sys
import zipfile

import openpyxl
import pytest

from docuworks_integrations import reviewed as r, reviewed_xlsx as x
from docuworks_integrations.cli import main
from test_reviewed import setup, read, write, hashes
from test_reviewed_v2 import modern


def fixture(tmp_path, monkeypatch, texts=('本文',), version='2.0'):
    run, session, sdk = (modern if version == '2.0' else setup)(tmp_path, monkeypatch)
    raw = read(session.review_xdw)
    seed = raw['pages'][0]['items'][0]
    raw['pages'][0]['items'] = [dict(copy.deepcopy(seed), text=text, x=2.25 + n, y=7.5,
                                    rotation=30, direction=n % 2) for n, text in enumerate(texts)]
    raw['pages'][1]['items'] = []
    if texts:
        raw['pages'][0]['items'][0]['identity'] = '{invalid'
    if version == '2.0':
        raw['pages'][0]['sticky_count'] = 2
    write(session.review_xdw, raw)
    result = r.import_reviewed_result(session.root, session.review_xdw, tmp_path / '校正結果 日本語',
                                     validation_mode='identity' if version == '2.0' else 'strict')
    return result


def text_value(value):
    # openpyxl exposes OOXML escaped CR in inline strings. Decode in one pass,
    # as required by ST_Xstring; literal "_x000D_" escapes must not be decoded twice.
    return re.sub(r'_x([0-9a-fA-F]{4})_', lambda m: chr(int(m[1], 16)), value or '')


def read_rows(path):
    book = openpyxl.load_workbook(path, read_only=True, data_only=False)
    try:
        return {sheet.title: list(sheet.iter_rows(values_only=True)) for sheet in book}
    finally:
        book.close()


@pytest.mark.parametrize('version', ['1.0', '2.0'])
def test_literal_values_geometry_metadata_and_source_immutable(tmp_path, monkeypatch, version):
    texts = [' 日本語 𠮷😀\t\n次\r\nCRLF\r末 ', '', ' \t ', '同文', '同文',
             '001234', '1234567890123456789012', '1-2', '1E10', '=SUM(1,2)',
             '+12', '-12', '@test', 'https://example.invalid/', '_x000D_ _x005F_']
    result = fixture(tmp_path, monkeypatch, texts, version)
    before = hashes(result.root)
    output = x.export_reviewed_xlsx(result, tmp_path / '全文.xlsx')
    rows = read_rows(output)
    assert list(rows) == ['全文一覧', '文書・ページ情報']
    assert rows['全文一覧'][0] == x.HEADERS
    assert [text_value(row[2]) for row in rows['全文一覧'][1:]] == texts
    for row, item in zip(rows['全文一覧'][1:], result.pages[0]['items']):
        assert row[:2] == (1, item['order'])
        assert row[3:5] == (1, 1)
        assert row[5:9] == tuple(item[k] for k in ('x', 'y', 'width', 'height'))
        assert row[10:12] == (30, item['item_id'])
    assert rows['全文一覧'][1][12] == 'invalid'
    info = {row[0]: row[1] for row in rows['文書・ページ情報'] if isinstance(row[0], str)}
    assert info['除外した付箋数'] == (2 if version == '2.0' else '記録なし')
    assert info['Reviewed manifest SHA-256'] == result.manifest_sha256
    assert info['文字項目数'] == len(texts)
    assert rows['文書・ページ情報'][-1][-1] == 0
    assert hashes(result.root) == before
    with zipfile.ZipFile(output) as z:
        xml = z.read('xl/worksheets/sheet1.xml')
        assert b'<f>' not in xml and b'<hyperlink ' not in xml
        assert b'<autoFilter ' in xml and b'<pane ' in xml


@pytest.mark.parametrize('text', ['A' * 32767, 'A' * 32768, '𠮷' * 16384,
                                 'A' * 32766 + '\r\n' + 'B', '\n' * 254,
                                 '行\r\n' * 600, '_x000D_' * 5000],
                         ids=['at-limit', 'over-limit', 'surrogates', 'crlf-boundary', 'lf-limit', 'crlf-many', 'literal-escape'])
def test_long_text_rejoins_without_loss(tmp_path, monkeypatch, text):
    result = fixture(tmp_path, monkeypatch, [text])
    output = x.export_reviewed_xlsx(result, tmp_path / '長文.xlsx')
    rows = read_rows(output)['全文一覧'][1:]
    values = [text_value(row[2]) for row in rows]
    assert ''.join(values) == text
    assert all(len(value.encode('utf-16-le')) // 2 <= 32767 and value.count('\n') <= 253 for value in values)
    assert not any(a.endswith('\r') and b.startswith('\n') for a, b in zip(values, values[1:]))
    assert [row[3] for row in rows] == list(range(1, len(rows) + 1))
    assert all(row[4] == len(rows) and row[11] == result.pages[0]['items'][0]['item_id'] for row in rows)


def test_sheet_rollover_and_empty_document(tmp_path, monkeypatch):
    result = fixture(tmp_path, monkeypatch, [str(i) for i in range(102)])
    monkeypatch.setattr(x, 'MAX_ROWS', 50)
    rows = read_rows(x.export_reviewed_xlsx(result, tmp_path / '分冊.xlsx'))
    assert list(rows) == ['全文一覧', '全文一覧_2', '全文一覧_3', '文書・ページ情報']
    assert [len(rows[n]) for n in list(rows)[:3]] == [50, 50, 5]
    values = [row[2] for name, sheet in rows.items() if name.startswith('全文一覧') for row in sheet[1:]]
    assert values == [str(i) for i in range(102)]


@pytest.mark.parametrize('version', ['1.0', '2.0'])
def test_no_items_still_has_all_pages(tmp_path, monkeypatch, version):
    result = fixture(tmp_path, monkeypatch, [], version)
    rows = read_rows(x.export_reviewed_xlsx(result, tmp_path / '空.xlsx'))
    assert len(rows['全文一覧']) == 1
    assert rows['文書・ページ情報'][-2][-1] == rows['文書・ページ情報'][-1][-1] == 0


@pytest.mark.parametrize('mode', ['existing', 'inside', 'wrong-suffix', 'tamper', 'during',
                                 'write', 'close', 'verify', 'publish', 'interrupt', 'illegal', 'row-code'])
def test_failure_never_publishes_or_changes_input(tmp_path, monkeypatch, mode):
    import xlsxwriter
    result = fixture(tmp_path, monkeypatch, ['bad\x01text' if mode == 'illegal' else '本文'])
    output = tmp_path / '失敗.xlsx'
    before = hashes(result.root)
    if mode == 'existing': output.write_bytes(b'keep')
    if mode == 'inside': output = result.root / 'bad.xlsx'
    if mode == 'wrong-suffix': output = tmp_path / 'bad.csv'
    if mode == 'tamper': (result.root / 'reviewed.jsonl').write_bytes(b'changed')
    def fail(*args, **kwargs): raise OSError('injected')
    if mode == 'write': monkeypatch.setattr(x, '_write_row', fail)
    if mode == 'close': monkeypatch.setattr(xlsxwriter.Workbook, 'close', fail)
    if mode == 'verify': monkeypatch.setattr(x, '_verify_workbook', fail)
    if mode == 'publish': monkeypatch.setattr(r, 'publish_new', fail)
    if mode == 'row-code': monkeypatch.setattr(xlsxwriter.worksheet.Worksheet, 'write_string', lambda *a, **k: -2)
    def progress(phase, *_):
        if phase == 'write' and mode == 'during': (result.root / 'reviewed.jsonl').write_bytes(b'changed')
        if phase == 'write' and mode == 'interrupt': raise KeyboardInterrupt()
    with pytest.raises((ValueError, RuntimeError, OSError, KeyboardInterrupt)):
        x.export_reviewed_xlsx(result, output, progress=progress)
    assert output.read_bytes() == b'keep' if mode == 'existing' else not output.exists()
    assert not list(tmp_path.glob('.reviewed-xlsx-*'))
    if mode not in ('tamper', 'during'): assert hashes(result.root) == before


def test_cli_and_lazy_dependencies(tmp_path, monkeypatch, capsys):
    result = fixture(tmp_path, monkeypatch)
    output = tmp_path / 'CLI.xlsx'
    assert main(['export-reviewed-xlsx', '--reviewed-dir', str(result.root), '--output', str(output)]) == 0
    assert '1文字項目 / 1行' in capsys.readouterr().out
    assert main(['export-reviewed-xlsx', '--reviewed-dir', str(result.root), '--output', str(output)]) == 1
    code = ('import sys; from docuworks_integrations import load_reviewed_result, export_reviewed_xlsx; '
            'assert "xlsxwriter" not in sys.modules; '
            'export_reviewed_xlsx(load_reviewed_result(sys.argv[1]),sys.argv[2]); '
            'assert all(m not in sys.modules for m in ("docuworks_ctypes","PIL","paddle","pandas","tkinter","openpyxl"))')
    subprocess.run([sys.executable, '-B', '-c', code, str(result.root), str(tmp_path / 'lazy.xlsx')], check=True)


def test_missing_optional_dependency_is_clear(tmp_path, monkeypatch):
    result = fixture(tmp_path, monkeypatch)
    monkeypatch.setitem(sys.modules, 'xlsxwriter', None)
    with pytest.raises(RuntimeError, match='ライブラリ'):
        x.export_reviewed_xlsx(result, tmp_path / 'missing.xlsx')
    assert not list(tmp_path.glob('.reviewed-xlsx-*'))


def test_destination_collision_before_publish_does_not_overwrite(tmp_path, monkeypatch):
    result = fixture(tmp_path, monkeypatch)
    output = tmp_path / 'race.xlsx'
    verify = x._verify_workbook
    def collide(*args):
        verify(*args)
        output.write_bytes(b'other writer')
    monkeypatch.setattr(x, '_verify_workbook', collide)
    with pytest.raises(FileExistsError):
        x.export_reviewed_xlsx(result, output)
    assert output.read_bytes() == b'other writer'
    assert not list(tmp_path.glob('.reviewed-xlsx-*'))


def test_linked_input_and_output_are_rejected(tmp_path, monkeypatch):
    result = fixture(tmp_path, monkeypatch)
    output = tmp_path / 'link.xlsx'
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda path: path == output or original(path))
    with pytest.raises(ValueError, match='linked'):
        x.export_reviewed_xlsx(result, output)
    monkeypatch.setattr(Path, 'is_symlink', lambda path: path == result.root or original(path))
    with pytest.raises(ValueError, match='linked'):
        x.export_reviewed_xlsx(result, output)
