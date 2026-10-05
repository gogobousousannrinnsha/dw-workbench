"""Synthetic acceptance tests: no real document, OCR engine, or native DLL."""
from dataclasses import asdict, replace
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

import pytest

from docuworks_integrations import (
    TextCorrection, save_corrections, load_corrections, apply_corrections,
    export_effective_jsonl,
)
from docuworks_integrations import corrections as module
from docuworks_integrations.results import load_ocr_result, save_ocr_result, export_jsonl, sha256
from test_canonical_results import fixture_result


def run(tmp_path, version='1.0', empty=False):
    result, assets = fixture_result(tmp_path, two=True)
    if version == '1.1':
        result = replace(result, schema_version=version, pages=tuple(
            replace(page, regions=() if empty or page.page == 2 else page.regions,
                    recognition_status='NO_TEXT_DETECTED' if empty or page.page == 2 else 'TEXT_DETECTED')
            for page in result.pages))
    return save_ocr_result(result, tmp_path / 'run', assets=assets)


def edit(text='訂正 "日本語"\n 前後空白 '):
    return TextCorrection('p0001-r000001', ' テスト ', text)


def tree_hash(root):
    return {p.relative_to(root).as_posix(): sha256(p) for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('version', ['1.0', '1.1'])
def test_roundtrip_preserves_source_and_coordinates(tmp_path, version):
    original = run(tmp_path, version)
    before = tree_hash(original.root)
    corrections = save_corrections(original.root, [edit()], tmp_path / 'corrections.json')
    assert corrections == load_corrections(corrections.path)
    assert corrections.correction_set_sha256 == sha256(corrections.path)
    payload = json.loads(corrections.path.read_text(encoding='utf-8'))
    assert 'path' not in payload and 'original_path' not in payload
    effective = apply_corrections(original.root, corrections)
    assert effective.source is not original.source
    assert effective.ocr is not original.ocr
    for old_page, page in zip(original.pages, effective.pages):
        for old, region in zip(old_page.regions, page.regions):
            data = asdict(region)
            data.pop('original_text'); data.pop('is_corrected')
            data['text'] = old.text
            assert data == asdict(old)
            assert region.bbox_px is not old.bbox_px
            assert region.original_text == old.text
    output = export_effective_jsonl(effective, tmp_path / 'effective.jsonl')
    rows = [json.loads(line) for line in output.read_text(encoding='utf-8').splitlines()]
    assert rows[0]['text'] == edit().after_text
    assert rows[0]['original_text'] == edit().before_text
    assert rows[0]['is_corrected'] is True
    assert rows[0]['correction_set_sha256'] == sha256(corrections.path)
    assert rows[0]['schema'] == module.EFFECTIVE_SCHEMA
    if version == '1.0':
        assert rows[1]['is_corrected'] is False
        assert rows[1]['text'] == rows[1]['original_text']
    raw = export_jsonl(original, tmp_path / 'original.jsonl')
    assert json.loads(raw.read_text(encoding='utf-8').splitlines()[0])['text'] == ' テスト '
    assert tree_hash(original.root) == before


@pytest.mark.parametrize('empty', [False, True])
def test_empty_set_and_empty_pages(tmp_path, empty):
    original = run(tmp_path, '1.1', empty=empty)
    corrections = save_corrections(original.root, [], tmp_path / 'corrections.json')
    effective = apply_corrections(original.root, corrections)
    out = export_effective_jsonl(effective, tmp_path / 'effective.jsonl')
    if empty:
        assert out.read_bytes() == b''
    else:
        assert not json.loads(out.read_text(encoding='utf-8'))['is_corrected']


@pytest.mark.parametrize('edits', [
    [edit('')], [edit(' \n\t')], [edit(' テスト ')], [edit(), edit()],
    [TextCorrection('p0009-r000001', ' テスト ', '修正')],
    [TextCorrection('p0001-r000001', 'テスト', '修正')],
    [TextCorrection(1, ' テスト ', '修正')],
    [TextCorrection('p0001-r000001', ' テスト ', 1)],
    [dict(region_id='p0001-r000001', before_text=' テスト ', after_text='修正')],
])
def test_invalid_edits_publish_nothing(tmp_path, edits):
    original = run(tmp_path)
    with pytest.raises(ValueError):
        save_corrections(original.root, edits, tmp_path / 'bad.json')
    assert not (tmp_path / 'bad.json').exists()


@pytest.mark.parametrize('change', [
    lambda p: p.update(schema_version='2.0'),
    lambda p: p.update(schema='wrong'),
    lambda p: p.update(extra=True),
    lambda p: p.pop('run_id'),
    lambda p: p.update(run_id=True),
    lambda p: p.update(correction_set_id='bad'),
    lambda p: p.update(manifest_sha256='bad'),
    lambda p: p.update(edits={}),
    lambda p: p['edits'][0].update(extra=1),
    lambda p: p['edits'].append(p['edits'][0].copy()),
], ids=['future', 'schema', 'extra', 'missing', 'run-type', 'set-id', 'hash', 'edits-type', 'edit-extra', 'duplicate'])
def test_malformed_file(tmp_path, change):
    original = run(tmp_path)
    corrections = save_corrections(original.root, [edit()], tmp_path / 'corrections.json')
    payload = json.loads(corrections.path.read_text(encoding='utf-8'))
    change(payload)
    corrections.path.write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(ValueError):
        load_corrections(corrections.path)


@pytest.mark.parametrize('content', ['{"a":1,"a":2}', '{"a":NaN}', '[]', '{broken'],
                         ids=['duplicate-key', 'nan', 'array', 'broken'])
def test_strict_json(tmp_path, content):
    path = tmp_path / 'bad.json'
    path.write_text(content, encoding='utf-8')
    with pytest.raises(ValueError):
        load_corrections(path)


@pytest.mark.parametrize('field,value', [('run_id', str(uuid.uuid4())), ('manifest_sha256', '0' * 64)])
def test_wrong_source(tmp_path, field, value):
    original = run(tmp_path)
    corrections = save_corrections(original.root, [edit()], tmp_path / 'corrections.json')
    payload = json.loads(corrections.path.read_text(encoding='utf-8'))
    payload[field] = value
    corrections.path.write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises((ValueError, RuntimeError)):
        apply_corrections(original.root, load_corrections(corrections.path))


def test_move_and_revision(tmp_path):
    original = run(tmp_path)
    first = save_corrections(original.root, [edit()], tmp_path / 'first.json')
    second = save_corrections(original.root, [edit('再訂正')], tmp_path / 'second.json')
    assert first.correction_set_id != second.correction_set_id
    moved = tmp_path / 'moved'
    moved.mkdir()
    shutil.move(str(original.root), str(moved / 'run'))
    shutil.move(str(second.path), str(moved / 'second.json'))
    effective = apply_corrections(moved / 'run', load_corrections(moved / 'second.json'))
    export_effective_jsonl(effective, moved / 'out.jsonl')
    assert effective.pages[0].regions[0].text == '再訂正'


@pytest.mark.parametrize('target', ['bbox', 'source', 'ocr', 'text', 'flag', 'set'])
def test_memory_modification_rejected(tmp_path, target):
    original = run(tmp_path)
    corrections = save_corrections(original.root, [edit()], tmp_path / 'corrections.json')
    effective = apply_corrections(original.root, corrections)
    if target == 'bbox': effective.pages[0].regions[0].bbox_px['x'] = 12
    elif target == 'source': effective.source['sha256'] = '0' * 64
    elif target == 'ocr': effective.ocr['modified'] = True
    elif target == 'text':
        page = effective.pages[0]
        effective = replace(effective, pages=(replace(page, regions=(replace(page.regions[0], text='bad'),)),))
    elif target == 'flag':
        object.__setattr__(effective.pages[0].regions[0], 'is_corrected', 1)
    else:
        effective = replace(effective, corrections=replace(corrections, edits=(edit('bad'),)))
    with pytest.raises(RuntimeError):
        export_effective_jsonl(effective, tmp_path / 'bad.jsonl')
    assert not (tmp_path / 'bad.jsonl').exists()
    assert load_ocr_result(original.root).pages[0].regions[0].bbox_px['x'] == 10


@pytest.mark.parametrize('target', ['corrections', 'manifest', 'asset'])
def test_disk_modification_rejected(tmp_path, target):
    original = run(tmp_path)
    corrections = save_corrections(original.root, [edit()], tmp_path / 'corrections.json')
    effective = apply_corrections(original.root, corrections)
    paths = {'corrections': corrections.path, 'manifest': original.root / 'manifest.json',
             'asset': original.root / original.pages[0].image}
    with paths[target].open('ab') as stream: stream.write(b' ')
    with pytest.raises(RuntimeError):
        export_effective_jsonl(effective, tmp_path / 'bad.jsonl')


def test_protected_destinations(tmp_path):
    original = run(tmp_path)
    path = tmp_path / 'corrections.json'
    corrections = save_corrections(original.root, [edit()], path)
    before = path.read_bytes()
    with pytest.raises(FileExistsError): save_corrections(original.root, [], path)
    assert path.read_bytes() == before
    with pytest.raises(ValueError): save_corrections(original.root, [], original.root / 'new.json')
    effective = apply_corrections(original.root, corrections)
    with pytest.raises(ValueError): export_effective_jsonl(effective, original.root / 'new.jsonl')
    with pytest.raises(FileExistsError): export_effective_jsonl(effective, path)
    inside = original.root / 'injected.json'
    shutil.copyfile(path, inside)
    with pytest.raises(ValueError): apply_corrections(original.root, load_corrections(inside))


@pytest.mark.parametrize('operation', ['save', 'export'])
@pytest.mark.parametrize('failure', ['write', 'publish', 'race', 'input'])
def test_atomic_failures(tmp_path, monkeypatch, operation, failure):
    original = run(tmp_path)
    corrections = save_corrections(original.root, [edit()], tmp_path / 'corrections.json')
    effective = apply_corrections(original.root, corrections)
    out = tmp_path / 'output.json'
    publish = module._publish_file
    fsync = module.os.fsync

    def failing_publish(temporary, output):
        if failure == 'race':
            output.write_text('existing', encoding='utf-8')
            return publish(temporary, output)
        raise OSError('injected publication failure')

    def modified_input(fd):
        fsync(fd)
        with (original.root / original.pages[0].image).open('ab') as stream: stream.write(b'changed')

    def failed_write(fd):
        raise OSError('injected disk flush failure')

    if failure in ('publish', 'race'): monkeypatch.setattr(module, '_publish_file', failing_publish)
    elif failure == 'input': monkeypatch.setattr(module.os, 'fsync', modified_input)
    else: monkeypatch.setattr(module.os, 'fsync', failed_write)
    with pytest.raises((OSError, RuntimeError)):
        if operation == 'save': save_corrections(original.root, [edit()], out)
        else: export_effective_jsonl(effective, out)
    if failure == 'race': assert out.read_text(encoding='utf-8') == 'existing'
    else: assert not out.exists()
    assert not list(tmp_path.glob('.correction-*.tmp'))


def test_legacy_run_without_conversion(tmp_path):
    root = tmp_path / 'legacy'
    root.mkdir()
    (root / 'source.xdw').write_bytes(b'synthetic source')
    for name in ('page.png', 'preview.png', 'regions.md'): (root / name).write_bytes(b'synthetic')
    (root / 'page-info.json').write_text(json.dumps(dict(page=1, page_width_mm=10,
        page_height_mm=10, pixel_width=100, pixel_height=100, source_sha256=sha256(root / 'source.xdw'))))
    (root / 'regions.json').write_text(json.dumps(dict(regions=[dict(region_id=1,
        text=' テスト ', confidence=.9, bbox=dict(x=10, y=10, width=20, height=10))])))
    files = {p.name: sha256(p) for p in root.iterdir()}
    (root / 'run.json').write_text(json.dumps(dict(schema_version=1, status='READY_FOR_SELECTION',
        files=files, source_sha256=files['source.xdw'], source_path='missing.xdw')))
    before = tree_hash(root)
    corrections = save_corrections(root, [edit()], tmp_path / 'corrections.json')
    effective = apply_corrections(root, corrections)
    export_effective_jsonl(effective, tmp_path / 'out.jsonl')
    assert corrections.manifest_sha256 == sha256(root / 'run.json')
    assert tree_hash(root) == before


def test_standard_library_only(tmp_path):
    original = run(tmp_path)
    package = str(Path(module.__file__).resolve().parents[1])
    code = '''
import sys
sys.path.insert(0, sys.argv[1])
class Block:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'docuworks_ctypes', 'PIL', 'paddle', 'paddleocr', 'paddlex', 'cv2', 'numpy', 'jsonschema'}:
            raise AssertionError('unexpected dependency: ' + fullname)
sys.meta_path.insert(0, Block())
from docuworks_integrations import TextCorrection, save_corrections, load_corrections, apply_corrections, export_effective_jsonl
c = save_corrections(sys.argv[2], [TextCorrection('p0001-r000001', ' テスト ', '修正')], sys.argv[3])
r = apply_corrections(sys.argv[2], load_corrections(c.path))
export_effective_jsonl(r, sys.argv[4])
'''
    subprocess.run([sys.executable, '-I', '-S', '-c', code, package, str(original.root),
                    str(tmp_path / 'corrections.json'), str(tmp_path / 'out.jsonl')], check=True)


def test_json_schemas(tmp_path):
    import jsonschema
    original = run(tmp_path)
    corrections = save_corrections(original.root, [edit()], tmp_path / 'corrections.json')
    effective = apply_corrections(original.root, corrections)
    out = export_effective_jsonl(effective, tmp_path / 'out.jsonl')
    package = Path(module.__file__).parent
    for name, values in [
        ('ocr-corrections-1.0.schema.json', [json.loads(corrections.path.read_text(encoding='utf-8'))]),
        ('ocr-effective-region-1.0.schema.json', [json.loads(line) for line in out.read_text(encoding='utf-8').splitlines()]),
    ]:
        schema = json.loads((package / name).read_text(encoding='utf-8'))
        jsonschema.Draft202012Validator.check_schema(schema)
        for value in values: jsonschema.validate(value, schema)


@pytest.mark.parametrize('field,value', [('region_id', 'p0003-r000001'), ('before_text', 'wrong')])
def test_reloaded_edits_are_matched_again(tmp_path, field, value):
    original = run(tmp_path)
    corrections = save_corrections(original.root, [edit()], tmp_path / 'corrections.json')
    payload = json.loads(corrections.path.read_text(encoding='utf-8'))
    payload['edits'][0][field] = value
    corrections.path.write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(ValueError):
        apply_corrections(original.root, load_corrections(corrections.path))


def test_partial_write_and_cleanup_failure_preserve_primary(tmp_path, monkeypatch):
    original = run(tmp_path)

    def partial(payload, stream, **kwargs):
        stream.write('{partial')
        raise OSError('disk full')

    unlink = Path.unlink

    def denied(path, *args, **kwargs):
        if path.name.startswith('.correction-'):
            raise PermissionError('cleanup denied')
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(module.json, 'dump', partial)
    monkeypatch.setattr(Path, 'unlink', denied)
    with pytest.raises(OSError, match='disk full') as exc:
        save_corrections(original.root, [edit()], tmp_path / 'bad.json')
    assert getattr(exc.value, '_ocr_cleanup_failed', False)
    assert not (tmp_path / 'bad.json').exists()


def test_correction_change_during_export(tmp_path, monkeypatch):
    original = run(tmp_path)
    corrections = save_corrections(original.root, [edit()], tmp_path / 'corrections.json')
    effective = apply_corrections(original.root, corrections)
    fsync = module.os.fsync

    def change(fd):
        fsync(fd)
        with corrections.path.open('ab') as stream: stream.write(b' ')

    monkeypatch.setattr(module.os, 'fsync', change)
    with pytest.raises(RuntimeError): export_effective_jsonl(effective, tmp_path / 'bad.jsonl')
    assert not (tmp_path / 'bad.jsonl').exists()


def test_output_page_order(tmp_path):
    original, assets = fixture_result(tmp_path, two=True)
    original = replace(original, pages=tuple(reversed(original.pages)))
    saved = save_ocr_result(original, tmp_path / 'run', assets=assets)
    corrections = save_corrections(saved.root, [edit()], tmp_path / 'corrections.json')
    out = export_effective_jsonl(apply_corrections(saved.root, corrections), tmp_path / 'out.jsonl')
    assert [json.loads(line)['page'] for line in out.read_text(encoding='utf-8').splitlines()] == [1, 2]
