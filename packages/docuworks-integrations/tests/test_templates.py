import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from docuworks_integrations import templates as t
from docuworks_integrations import reviewed as r


def attr(value, kind='STRING'): return dict(kind=kind, value=value)


def rectangle(order=1, purpose='取得', name='温度', **attrs):
    attributes = {'用途': attr(purpose), '項目名': attr(name), **attrs}
    return dict(annotation_order=order, x=10, y=10, width=80, height=20, attributes=attributes)


def snapshot():
    return dict(pages=[dict(page=1, width_mm=210, height_mm=297, rotation=0,
                           rectangles=[rectangle(), rectangle(3, '適用判定', '帳票', 期待文字=attr('帳簿A'))]),
                       dict(page=2, width_mm=210, height_mm=297, rotation=0, rectangles=[])])


def setup_template(tmp_path, monkeypatch, data=None, output='template'):
    source = tmp_path/'帳簿A.xdw'
    source.write_bytes(b'disposable fake XDW')
    class Backend:
        def inspect(self, path): return copy.deepcopy(snapshot() if data is None else data)
    monkeypatch.setattr(t, '_sdk', lambda dll: Backend())
    return t.register_rectangle_template(source, tmp_path/output)


def test_registration_freezes_definition_without_native_loader(tmp_path, monkeypatch):
    saved = setup_template(tmp_path, monkeypatch)
    before = (tmp_path/'帳簿A.xdw').read_bytes()
    assert saved.data['name'] == '帳簿A'
    assert saved.data['pages'][0]['rectangles'][0]['join'] == '連結'
    assert saved.data['pages'][0]['rectangles'][0]['required'] is True
    assert saved.data['coordinate_basis'] == 'reviewed'
    changed = saved.data; changed['pages'].clear()
    assert len(saved.data['pages']) == 2
    def fail(*args): raise AssertionError('saved load must not open SDK')
    monkeypatch.setattr(t, '_sdk', fail)
    (tmp_path/'帳簿A.xdw').unlink()
    assert t.load_rectangle_template(saved.root) == saved
    assert (saved.root/'source-template.xdw').read_bytes() == before


@pytest.mark.parametrize('mode', ['purpose', 'name', 'duplicate', 'expected', 'space-expected', 'kind',
    'join', 'required', 'order', 'out', 'negative', 'zero', 'rotation', 'no-fields', 'no-pages', 'condition-field-attr'])
def test_invalid_template_is_not_published(tmp_path, monkeypatch, mode):
    data = snapshot(); page = data['pages'][0]; first = page['rectangles'][0]; attrs = first['attributes']
    if mode == 'purpose': attrs.pop('用途')
    if mode == 'name': attrs['項目名'] = attr('  ')
    if mode == 'duplicate': page['rectangles'].append(rectangle(4))
    if mode == 'expected': page['rectangles'][1]['attributes'].pop('期待文字')
    if mode == 'space-expected': page['rectangles'][1]['attributes']['期待文字'] = attr(' 帳簿A ')
    if mode == 'kind': attrs['項目名'] = attr('温度', 'BOOL')
    if mode == 'join': attrs['結合方法'] = attr('guess')
    if mode == 'required': attrs['必須'] = attr(1, 'BOOL')
    if mode == 'order': attrs['出力順'] = attr(True, 'INT')
    if mode == 'out': first['width'] = 300
    if mode == 'negative': first['x'] = -1
    if mode == 'zero': first['height'] = 0
    if mode == 'rotation': page['rotation'] = 180
    if mode == 'no-fields': page['rectangles'].pop(0)
    if mode == 'no-pages': data['pages'] = []
    if mode == 'condition-field-attr': page['rectangles'][1]['attributes']['必須'] = attr(False, 'BOOL')
    with pytest.raises(ValueError): setup_template(tmp_path, monkeypatch, data)
    assert not (tmp_path/'template').exists()


@pytest.mark.parametrize('failure', ['sdk', 'race', 'write', 'publish'])
def test_registration_failure_is_atomic(tmp_path, monkeypatch, failure):
    source = tmp_path/'source.xdw'; source.write_bytes(b'source')
    class Backend:
        def inspect(self, path):
            if failure == 'sdk': raise OSError('SDK read failed')
            if failure == 'race': source.write_bytes(b'changed concurrently')
            return snapshot()
    monkeypatch.setattr(t, '_sdk', lambda dll: Backend())
    def fail(*args): raise OSError('write failed')
    if failure == 'write': monkeypatch.setattr(r, '_write_manifest', fail)
    if failure == 'publish': monkeypatch.setattr(r, 'publish_new', fail)
    with pytest.raises((OSError, RuntimeError)):
        t.register_rectangle_template(source, tmp_path/'output')
    assert not (tmp_path/'output').exists()
    if failure != 'race': assert source.read_bytes() == b'source'


@pytest.mark.parametrize('file', ['template.json', 'source-template.xdw', 'manifest.json'])
def test_corruption(tmp_path, monkeypatch, file):
    saved = setup_template(tmp_path, monkeypatch)
    with (saved.root/file).open('ab') as stream: stream.write(b'bad')
    with pytest.raises((ValueError, RuntimeError)): t.load_rectangle_template(saved.root)


def test_rehashed_bad_geometry_and_protected_destinations(tmp_path, monkeypatch):
    saved = setup_template(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        t.register_rectangle_template(tmp_path/'帳簿A.xdw', saved.root/'nested')
    with pytest.raises(ValueError): t.load_rectangle_template(tmp_path/'.rectangle-template-private')
    data = saved.data; data['pages'][0]['rectangles'][0]['x'] = -1
    (saved.root/'template.json').write_bytes(r._bytes(data))
    r._write_manifest(saved.root, t.SCHEMA, t.FILES)
    with pytest.raises(ValueError): t.load_rectangle_template(saved.root)


def test_schema_and_lazy_import(tmp_path, monkeypatch):
    import jsonschema
    saved = setup_template(tmp_path, monkeypatch)
    for filename, schema in [('template.json','rectangle-template'), ('manifest.json','rectangle-template-manifest')]:
        definition = json.loads(Path(t.__file__).with_name(schema+'-1.0.schema.json').read_bytes())
        jsonschema.Draft202012Validator.check_schema(definition)
        jsonschema.validate(json.loads((saved.root/filename).read_bytes()), definition, format_checker=jsonschema.FormatChecker())
    subprocess.run([sys.executable,'-B','-c',
        "import sys; from docuworks_integrations import register_rectangle_template, load_rectangle_template; assert 'docuworks_ctypes' not in sys.modules; assert 'PIL' not in sys.modules"],check=True)
