"""Review coordination tests using a file-backed fake native boundary."""
from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

import pytest

from docuworks_integrations import create_review_xdw, read_review_edit, save_corrections, apply_corrections, export_effective_jsonl
from docuworks_integrations import review_xdw as review
from docuworks_integrations.results import load_ocr_result, sha256
from test_corrections import run, tree_hash


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')


class FakeSdk:
    def __init__(self, page):
        self.page = page
        self.background = []
        self.extracted_page = None

    def extract(self, source, page, output):
        self.extracted_page = page
        write(output, dict(width=self.page.page_width_mm, height=self.page.page_height_mm,
                           pages=1, annotations=self.background))

    def inspect(self, path):
        data = read(path)
        if data['pages'] != 1: raise ValueError('review XDW must contain exactly one page')
        annotations = []
        for item in data['annotations']:
            item = dict(item)
            if item['identity'] is not None: item['identity'] = item['identity'].encode('utf-8')
            annotations.append(review._Annotation(**item))
        return review._Page(data['width'], data['height'], tuple(annotations))

    def add_text(self, path, region, identity):
        data = read(path)
        data['annotations'].append(dict(kind='text', identity=identity.decode('utf-8'), text=region.text,
                                        x=region.bbox_mm['x'], y=region.bbox_mm['y']))
        write(path, data)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    original = run(tmp_path)
    sdk = FakeSdk(original.pages[1])
    monkeypatch.setattr(review, '_SdkBackend', lambda dll: sdk)
    return original, sdk


def create(setup, tmp_path):
    original, sdk = setup
    root = create_review_xdw(original.root, 'p0002-r000001', tmp_path / 'review')
    edited = tmp_path / 'edited.xdw'
    shutil.copyfile(root / 'review.xdw', edited)
    return original, sdk, root, edited


def test_complete_roundtrip(setup, tmp_path):
    original, sdk = setup
    before = tree_hash(original.root)
    sdk.background = [dict(kind='other', identity=None, text=None, x=1, y=2)]
    original, sdk, root, edited = create(setup, tmp_path)
    assert sdk.extracted_page == 2 and read(root / 'review.json')['review_page'] == 1
    assert read(edited)['annotations'][0] == sdk.background[0]
    data = read(edited)
    data['annotations'][1].update(text=' 訂正\n"日本語" ', x=9, y=8)
    write(edited, data)
    candidate = read_review_edit(original.root, root, edited)
    assert candidate.correction.region_id == 'p0002-r000001'
    assert candidate.correction.before_text == original.pages[1].regions[0].text
    assert candidate.edited_xdw_sha256 == sha256(edited)
    corrections = save_corrections(original.root, [candidate.correction], tmp_path / 'corrections.json')
    effective = apply_corrections(original.root, corrections)
    out = export_effective_jsonl(effective, tmp_path / 'out.jsonl')
    rows = [json.loads(line) for line in out.read_text(encoding='utf-8').splitlines()]
    assert rows[1]['text'] == ' 訂正\n"日本語" '
    assert rows[1]['page'] == 2 and rows[0]['is_corrected'] is False
    assert rows[1]['bbox_mm'] == original.pages[1].regions[0].bbox_mm
    assert tree_hash(original.root) == before


def test_unchanged_empty_set(setup, tmp_path):
    original, _, root, edited = create(setup, tmp_path)
    candidate = read_review_edit(original.root, root, edited)
    assert candidate.correction is None
    saved = save_corrections(original.root, [], tmp_path / 'empty.json')
    assert saved.edits == ()


@pytest.mark.parametrize('value', ['', ' \n\t'])
def test_blank_validation_belongs_to_corrections(setup, tmp_path, value):
    original, _, root, edited = create(setup, tmp_path)
    data = read(edited)
    data['annotations'][0]['text'] = value
    write(edited, data)
    candidate = read_review_edit(original.root, root, edited)
    with pytest.raises(ValueError, match='nonblank'):
        save_corrections(original.root, [candidate.correction], tmp_path / 'bad.json')
    assert not (tmp_path / 'bad.json').exists()


@pytest.mark.parametrize('change', ['delete', 'missing', 'empty', 'broken', 'duplicate', 'plain-copy', 'type', 'pages', 'dimensions', 'foreign'])
def test_reject_invalid_edited_xdw(setup, tmp_path, change):
    original, _, root, edited = create(setup, tmp_path)
    data = read(edited)
    target = data['annotations'][0]
    if change == 'delete': data['annotations'] = []
    elif change == 'missing': target['identity'] = None
    elif change == 'empty': target['identity'] = ''
    elif change == 'broken': target['identity'] = '{bad'
    elif change == 'duplicate': data['annotations'].append(target.copy())
    elif change == 'plain-copy': data['annotations'].append(dict(target, identity=None))
    elif change == 'type': target['kind'] = 'other'
    elif change == 'pages': data['pages'] = 2
    elif change == 'dimensions': data['width'] += 1
    else:
        identity = json.loads(target['identity'])
        identity['review_id'] = str(uuid.uuid4())
        target['identity'] = json.dumps(identity)
    write(edited, data)
    with pytest.raises(ValueError): read_review_edit(original.root, root, edited)


@pytest.mark.parametrize('field,value', [('schema_version','2.0'), ('annotation_count', True), ('annotation_count',2),
    ('source_page',1), ('review_page',2), ('page_width_mm',999), ('original_text','bad'), ('extra',1),
    ('run_id',str(uuid.uuid4())), ('manifest_sha256','0'*64)])
def test_manifest_invalid_or_changed(setup, tmp_path, field, value):
    original, _, root, edited = create(setup, tmp_path)
    data = read(root / 'review.json')
    data[field] = value
    write(root / 'review.json', data)
    with pytest.raises(ValueError): read_review_edit(original.root, root, edited)


def test_different_review_set_same_run(setup, tmp_path):
    original, _, root, edited = create(setup, tmp_path)
    other = create_review_xdw(original.root, 'p0002-r000001', tmp_path / 'other')
    with pytest.raises(ValueError): read_review_edit(original.root, other, edited)


def test_moving_review_and_run(setup, tmp_path):
    original, _, root, edited = create(setup, tmp_path)
    shutil.move(str(root), str(tmp_path / 'moved-review'))
    shutil.move(str(original.root), str(tmp_path / 'moved-run'))
    assert read_review_edit(tmp_path / 'moved-run', tmp_path / 'moved-review', edited).correction is None


def test_collision_and_destination_protection(setup, tmp_path):
    original, sdk, root, edited = create(setup, tmp_path)
    before = tree_hash(root)
    with pytest.raises(FileExistsError): create_review_xdw(original.root,'p0002-r000001',root)
    assert tree_hash(root) == before
    with pytest.raises(ValueError): create_review_xdw(original.root,'p0002-r000001',original.root / 'review')
    sdk.background = read(edited)['annotations']
    with pytest.raises(ValueError, match='reserved'):
        create_review_xdw(original.root,'p0002-r000001',tmp_path / 'collision')
    assert not (tmp_path / 'collision').exists()


@pytest.mark.parametrize('operation', ['save', 'publish', 'race', 'source', 'lost-identity'])
def test_generation_failures_do_not_publish(setup, tmp_path, monkeypatch, operation):
    original, sdk = setup
    out = tmp_path / 'bad'
    add = sdk.add_text
    publish = review.publish_new

    def fail_add(path, region, identity):
        add(path, region, identity)
        if operation == 'save': raise OSError('save failed')
        if operation == 'source':
            with (original.root / original.pages[0].image).open('ab') as f: f.write(b'changed')
        if operation == 'lost-identity':
            data = read(path); data['annotations'][0]['identity'] = None; write(path, data)

    def fail_publish(source, dest):
        if operation == 'race':
            dest.mkdir(); (dest / 'keep').write_text('keep')
            publish(source, dest)
        raise OSError('publish failed')

    monkeypatch.setattr(sdk, 'add_text', fail_add)
    if operation in ('publish','race'): monkeypatch.setattr(review,'publish_new',fail_publish)
    with pytest.raises((OSError, ValueError, RuntimeError)):
        create_review_xdw(original.root,'p0002-r000001',out)
    if operation == 'race': assert (out / 'keep').read_text() == 'keep'
    else: assert not out.exists()
    assert not list(tmp_path.glob('.review-*'))


@pytest.mark.parametrize('which', ['xdw','manifest','source'])
def test_changes_during_import(setup, tmp_path, monkeypatch, which):
    original, sdk, root, edited = create(setup, tmp_path)
    inspect = sdk.inspect
    path = {'xdw':edited,'manifest':root / 'review.json','source':original.root / original.pages[0].image}[which]
    def changed(p):
        result = inspect(p)
        with path.open('ab') as f: f.write(b' ')
        return result
    monkeypatch.setattr(sdk, 'inspect', changed)
    with pytest.raises(RuntimeError): read_review_edit(original.root,root,edited)


def test_import_does_not_load_native_dependencies():
    package = str(Path(review.__file__).resolve().parents[1])
    code = '''
import sys
sys.path.insert(0,sys.argv[1])
class Block:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'docuworks_ctypes','PIL','paddle','paddleocr','numpy'}:
            raise AssertionError(fullname)
sys.meta_path.insert(0,Block())
from docuworks_integrations import create_review_xdw, read_review_edit
'''
    subprocess.run([sys.executable,'-I','-S','-c',code,package],check=True)


@pytest.mark.parametrize('size,data_result,expected', [(-2147024809,None,'missing'), (-2147024891,None,'error'),
    (0,None,'empty'), (4,-2147024809,'error'), (4,5,'changed')])
def test_only_missing_size_query_is_ignored(size, data_result, expected):
    from types import SimpleNamespace
    from docuworks_ctypes.errors import XdwError
    def get(*args): return size if args[3] == 0 else data_result
    annotation = SimpleNamespace(raw=SimpleNamespace(XDW_GetAnnotationUserAttribute=get), handle=None)
    if expected == 'missing': assert review._SdkBackend._attribute(annotation) is None
    elif expected == 'empty': assert review._SdkBackend._attribute(annotation) == b''
    else:
        with pytest.raises(RuntimeError if expected == 'changed' else XdwError):
            review._SdkBackend._attribute(annotation)


def test_review_schema(setup, tmp_path):
    import jsonschema
    _, _, root, edited = create(setup, tmp_path)
    schema = read(Path(review.__file__).with_name('ocr-review-1.0.schema.json'))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(read(root / 'review.json'),schema)
    jsonschema.validate(json.loads(read(edited)['annotations'][0]['identity']),schema)


def test_private_or_invalid_inputs(setup, tmp_path):
    original, _, root, edited = create(setup, tmp_path)
    for region_id in (1, '1', 'p0099-r000001'):
        with pytest.raises(ValueError): create_review_xdw(original.root,region_id,tmp_path/'bad')
    private=tmp_path/('.review-'+uuid.uuid4().hex)
    with pytest.raises(ValueError): create_review_xdw(original.root,'p0002-r000001',private)
    shutil.copytree(root,private)
    with pytest.raises(ValueError): read_review_edit(original.root,private,edited)
    with pytest.raises(ValueError): read_review_edit(original.root,root,original.root/'source/source.xdw')
