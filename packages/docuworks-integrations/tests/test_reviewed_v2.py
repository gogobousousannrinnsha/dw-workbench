"""Format 2.0 acceptance contracts, including legacy compatibility and failure paths."""
import base64
import copy
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from docuworks_integrations import reviewed as m
from docuworks_integrations import _reviewed_v2 as v2
from test_reviewed import setup, read, write, hashes


def modern(tmp_path, monkeypatch, *, empty=False):
    run, session, sdk = setup(tmp_path, monkeypatch, empty=empty, version='1.1' if empty else '1.0')
    inspect = sdk.inspect

    def inspect_v2(path, *, exclude_sticky=False):
        data = inspect(path)
        sticky_count = sum(p.pop('sticky_count', 0) for p in data['pages'])
        if exclude_sticky:
            data['excluded_sticky_count'] = sticky_count
        elif sticky_count:
            raise ValueError('nested text unsupported')
        return data

    def set_origins(path, updates):
        data = read(path)
        for update in updates:
            data['pages'][update['page']-1]['items'][update['order']-1]['identity'] = json.loads(update['raw'])
        write(path, data)

    monkeypatch.setattr(sdk, 'inspect', inspect_v2)
    monkeypatch.setattr(sdk, 'set_origins', set_origins, raising=False)
    return run, session, sdk


def take(session, output):
    return m.import_reviewed_result(session.root, session.review_xdw, output, validation_mode='identity')


def payload(session, ids=None):
    identity = session.identity
    if ids is None:
        ids = [i['region_id'] for p in identity['pages'] for i in p['items']]
    return dict(schema=v2.ORIGIN_SCHEMA, schema_version='2.0', review_id=session.review_id,
                identity_sha256=m._digest(session._identity_bytes), origins=[v2.reference(identity, i) for i in ids])


@pytest.mark.parametrize('empty', [False, True])
def test_identity_roundtrip_and_offline_load(tmp_path, monkeypatch, empty):
    run, session, _ = modern(tmp_path, monkeypatch, empty=empty)
    before = hashes(run.root), hashes(session.root)
    result = take(session, tmp_path/'result')
    assert result.data['schema_version'] == '2.0'
    assert result.data['validation'] == v2.VALIDATION
    assert result.data['excluded_sticky_count'] == 0
    assert len(result.pages) == 2
    assert (hashes(run.root), hashes(session.root)) == before
    assert result.pages[0]['page_id'] != session.pages[0]['page_id']
    if empty:
        assert all(not p['items'] for p in result.pages)
        assert (result.root/'reviewed.jsonl').read_bytes() == b''
    shutil.move(run.root, tmp_path/'offline-run')
    again = take(session, tmp_path/'again')
    assert result.result_id != again.result_id
    shutil.move(session.root, tmp_path/'offline-session')
    assert m.load_reviewed_result(result.root) == result
    assert m.export_reviewed_jsonl(result, tmp_path/'export.jsonl').read_bytes() == (result.root/'reviewed.jsonl').read_bytes()


@pytest.mark.parametrize('mode', ['missing', 'explicit-empty', 'multi', 'shared', 'invalid', 'foreign',
                                  'partial-invalid', 'partial-foreign', 'malformed', 'legacy-bad', 'deep'])
def test_provenance_does_not_reject_text(tmp_path, monkeypatch, mode):
    _, session, _ = modern(tmp_path, monkeypatch)
    data = read(session.review_xdw)
    first = data['pages'][0]['items'][0]
    value = payload(session)
    assert len(value['origins']) == 2
    if mode == 'missing': value = None
    if mode == 'explicit-empty': value['origins'] = []
    if mode == 'invalid': value['origins'][0]['region_id'] = 'unknown'; value['origins'].pop()
    if mode == 'foreign': value['review_id'] = '00000000-0000-0000-0000-000000000000'
    if mode == 'partial-invalid': value['origins'][1]['region_id'] = 'unknown'
    if mode == 'partial-foreign': value['origins'][1]['run_id'] = '00000000-0000-0000-0000-000000000000'
    if mode == 'malformed': value = '{broken'
    if mode == 'legacy-bad': value = dict(first['identity'], region_id='unknown')
    if mode == 'deep': value = '{"x":' + '[' * 2000 + '0' + ']' * 2000 + '}'
    first.update(text=' ８０ ℃\n𠮷😀 ', identity=value)
    if mode == 'shared': data['pages'][1]['items'].append(copy.deepcopy(first))
    write(session.review_xdw, data)
    result = take(session, tmp_path/'result')
    item = result.pages[0]['items'][0]
    assert item['text'] == first['text']
    expected = {'missing':'none', 'explicit-empty':'none', 'multi':'matched', 'shared':'matched',
                'foreign':'foreign', 'partial-invalid':'partial', 'partial-foreign':'partial'}.get(mode, 'invalid')
    assert item['origin_evidence']['status'] == expected
    if expected in ('none', 'matched'): assert item['diagnostics'] == []
    else: assert item['diagnostics'] == ['ORIGIN_' + expected.upper()]
    assert len(item['origins']) == (2 if expected == 'matched' else 1 if expected == 'partial' else 0)
    assert m.load_reviewed_result(result.root) == result
    if mode == 'shared': assert result.pages[1]['items'][-1]['origins'] == item['origins']


@pytest.mark.parametrize('change', ['extra', 'fewer', 'reorder', 'dimensions', 'rotation', 'page-id'])
def test_identity_mode_records_all_actual_pages_without_claiming_structure_support(tmp_path, monkeypatch, change):
    _, session, _ = modern(tmp_path, monkeypatch)
    data = read(session.review_xdw)
    if change == 'extra': data['pages'].append(copy.deepcopy(data['pages'][0]))
    if change == 'fewer': data['pages'].pop()
    if change == 'reorder': data['pages'].reverse()
    if change == 'dimensions': data['pages'][0].update(width_mm=333, height_mm=444)
    if change == 'rotation': data['pages'][0]['rotation'] = 180
    if change == 'page-id': data['pages'][0]['identity'] = None
    for index, page in enumerate(data['pages'], 1): page['page'] = index
    write(session.review_xdw, data)
    with pytest.raises(ValueError):
        m.import_reviewed_result(session.root, session.review_xdw, tmp_path/'strict')
    result = take(session, tmp_path/'result')
    assert len(result.pages) == len(data['pages'])
    for actual, expected in zip(result.pages, data['pages']):
        assert all(actual[k] == expected[k] for k in ('page', 'width_mm', 'height_mm', 'rotation'))
        assert len(actual['items']) == len(expected['items'])
    assert result.data['validation']['page_structure_checked'] is False
    assert m.load_reviewed_result(result.root) == result


@pytest.mark.parametrize('change', ['missing-doc', 'foreign-doc', 'corrupt-doc', 'group', 'unreadable', 'empty-text', 'delete'])
def test_failure_vs_empty_text_and_deletion(tmp_path, monkeypatch, change):
    _, session, _ = modern(tmp_path, monkeypatch)
    first_result = take(session, tmp_path/'first')
    before = hashes(first_result.root)
    data = read(session.review_xdw)
    if change == 'missing-doc': data['identity'] = None
    if change == 'foreign-doc': data['identity']['identity_sha256'] = '0'*64
    if change == 'corrupt-doc': data['identity'] = '{broken'
    if change == 'group': data['pages'][0]['nested'] = True
    if change == 'unreadable': data['pages'][0]['items'][0]['text'] = None
    if change == 'empty-text': data['pages'][0]['items'][0]['text'] = ' \u3000\n'
    if change == 'delete':
        for page in data['pages']: page['items'] = []
    write(session.review_xdw, data)
    if change in ('empty-text', 'delete'):
        result = take(session, tmp_path/'second')
        if change == 'empty-text':
            assert result.pages[0]['items'][0]['text'] == ' \u3000\n'
            assert result.pages[0]['items'][0]['diagnostics'] == ['EMPTY_TEXT']
        else: assert all(p['items'] == [] for p in result.pages)
    else:
        with pytest.raises(ValueError): take(session, tmp_path/'second')
        assert not (tmp_path/'second').exists()
    assert hashes(first_result.root) == before


def test_assignment_preserves_input_and_sets_multiple_or_empty_refs(tmp_path, monkeypatch):
    run, session, _ = modern(tmp_path, monkeypatch)
    before = hashes(run.root), hashes(session.root)
    ids = [i['region_id'] for p in session.identity['pages'] for i in p['items']]
    assignments = [dict(page=1, order=1, region_ids=ids+ids), dict(page=2, order=1, region_ids=[])]
    edited = m.set_review_origins(session.root, session.review_xdw, tmp_path/'assigned.xdw', assignments,
                                 expected_source_sha256=m.sha256(session.review_xdw))
    result = m.import_reviewed_result(session.root, edited, tmp_path/'result', validation_mode='identity')
    assert m.get_reviewed_origins(result.pages[0]['items'][0]) == tuple(sorted(ids))
    assert m.get_reviewed_origins(result.pages[1]['items'][0]) == ()
    assert result.pages[1]['items'][0]['diagnostics'] == []
    assert (hashes(run.root), hashes(session.root)) == before


@pytest.mark.parametrize('change', ['stale', 'unknown', 'bad-page', 'bad-order', 'duplicate', 'save-failure', 'readback', 'race', 'publish'])
def test_assignment_rejects_wrong_targets_and_publishes_atomically(tmp_path, monkeypatch, change):
    _, session, sdk = modern(tmp_path, monkeypatch)
    old = m.sha256(session.review_xdw)
    ids = [i['region_id'] for p in session.identity['pages'] for i in p['items']]
    assignments = [dict(page=1, order=1, region_ids=ids)]
    expected = old
    if change == 'stale': expected = '0'*64
    if change == 'unknown': assignments[0]['region_ids'] = ['missing']
    if change == 'bad-page': assignments[0]['page'] = True
    if change == 'bad-order': assignments[0]['order'] = 99
    if change == 'duplicate': assignments *= 2
    setter = sdk.set_origins
    def changed(path, updates):
        if change == 'save-failure': raise OSError('save failed')
        if change != 'readback': setter(path, updates)
        if change == 'race':
            with session.review_xdw.open('ab') as stream: stream.write(b' ')
    if change in ('save-failure', 'readback', 'race'): monkeypatch.setattr(sdk, 'set_origins', changed)
    if change == 'publish':
        def fail(*args): raise OSError('publish failed')
        monkeypatch.setattr(m, 'publish_new', fail)
    with pytest.raises((ValueError, RuntimeError, OSError)):
        m.set_review_origins(session.root, session.review_xdw, tmp_path/'assigned.xdw', assignments,
                             expected_source_sha256=expected)
    assert not (tmp_path/'assigned.xdw').exists()
    if change != 'race': assert m.sha256(session.review_xdw) == old


@pytest.mark.parametrize('change', ['origins', 'evidence', 'diagnostics', 'scope', 'scope-bool', 'count', 'page-id', 'order', 'jsonl', 'version'])
def test_rehashed_invalid_results_are_rejected(tmp_path, monkeypatch, change):
    _, session, _ = modern(tmp_path, monkeypatch)
    result = take(session, tmp_path/'result')
    data = read(result.root/'reviewed.json'); item = data['pages'][0]['items'][0]
    if change == 'origins': item['origins'] = []
    if change == 'evidence': item['origin_evidence']['raw_base64'] = None
    if change == 'diagnostics': item['diagnostics'] = ['ORIGIN_MISSING']
    if change == 'scope': data['validation']['page_structure_checked'] = True
    if change == 'scope-bool': data['validation']['identity_checked'] = 1
    if change == 'count': data['excluded_sticky_count'] = -1
    if change == 'page-id': data['pages'][1]['page_id'] = data['pages'][0]['page_id']
    if change == 'order': item['order'] = True
    if change == 'version': data['schema_version'] = '1.0'
    write(result.root/'reviewed.json', data)
    (result.root/'reviewed.jsonl').write_bytes(b'bad' if change == 'jsonl' else v2.jsonl(data))
    m._write_manifest(result.root, m.RESULT_SCHEMA, m.RESULT_FILES, '2.0')
    with pytest.raises(ValueError): m.load_reviewed_result(result.root)


@pytest.mark.parametrize('name', sorted(m.RESULT_FILES) + ['manifest.json'])
def test_corrupt_saved_files(tmp_path, monkeypatch, name):
    _, session, _ = modern(tmp_path, monkeypatch)
    result = take(session, tmp_path/'result')
    with (result.root/name).open('ab') as stream: stream.write(b'bad')
    with pytest.raises((ValueError, RuntimeError)): m.load_reviewed_result(result.root)


@pytest.mark.parametrize('change', ['sdk', 'source-race', 'session-race', 'save', 'publish'])
def test_identity_import_failure_does_not_publish_or_change_existing_results(tmp_path, monkeypatch, change):
    run, session, sdk = modern(tmp_path, monkeypatch)
    existing = take(session, tmp_path/'existing')
    stable = hashes(run.root), hashes(existing.root)
    source_hash = m.sha256(session.review_xdw)
    inspect = sdk.inspect
    def changed(path, **kwargs):
        if change == 'sdk': raise OSError('native read failed')
        snapshot = inspect(path, **kwargs)
        target = session.review_xdw if change == 'source-race' else session.root/'session.json'
        if change.endswith('-race'):
            with target.open('ab') as stream: stream.write(b' ')
        return snapshot
    monkeypatch.setattr(sdk, 'inspect', changed)
    def fail(*args, **kwargs): raise OSError('save or publish failed')
    if change == 'publish': monkeypatch.setattr(m, 'publish_new', fail)
    if change == 'save': monkeypatch.setattr(m, '_write_manifest', fail)
    with pytest.raises((OSError, RuntimeError, ValueError)):
        take(session, tmp_path/'failed')
    assert not (tmp_path/'failed').exists()
    assert (hashes(run.root), hashes(existing.root)) == stable
    if change != 'source-race': assert m.sha256(session.review_xdw) == source_hash


def test_identity_destinations_and_initial_remain_protected(tmp_path, monkeypatch):
    run, session, _ = modern(tmp_path, monkeypatch)
    result = take(session, tmp_path/'existing')
    stable = hashes(run.root), hashes(session.root), hashes(result.root)
    for target in (run.root/'bad', session.root/'bad', result.root/'bad', result.root):
        with pytest.raises((ValueError, FileExistsError)):
            take(session, target)
    with pytest.raises(ValueError):
        m.import_reviewed_result(session.root, session.root/'initial.xdw', tmp_path/'bad', validation_mode='identity')
    with pytest.raises(ValueError):
        m.import_reviewed_result(session.root, session.review_xdw, tmp_path/'bad', validation_mode='unknown')
    assert (hashes(run.root), hashes(session.root), hashes(result.root)) == stable


def test_legacy_reading_and_common_reference_access(tmp_path, monkeypatch):
    _, session, _ = modern(tmp_path, monkeypatch)
    data = read(session.review_xdw)
    data['pages'][0]['items'].append(copy.deepcopy(data['pages'][0]['items'][0]))
    data['pages'][1]['items'][0]['identity'] = None
    write(session.review_xdw, data)
    old = m.import_reviewed_result(session.root, session.review_xdw, tmp_path/'legacy')
    before = hashes(old.root)
    loaded = m.load_reviewed_result(old.root)
    assert loaded.data['schema_version'] == '1.0'
    assert loaded.pages[0]['items'][0]['origin']['status'] == 'duplicate'
    assert len(m.get_reviewed_origins(loaded.pages[0]['items'][0])) == 1
    assert m.get_reviewed_origins(loaded.pages[1]['items'][0]) == ()
    assert hashes(old.root) == before


def test_sticky_ownership_not_visual_overlap():
    from docuworks_ctypes import AnnotationType as A
    from docuworks_integrations._reviewed_sdk import ReviewSdk
    class Node:
        def __init__(self, kind, children=()):
            self.annotation_type = kind; self.handle = id(self)
            self._info = SimpleNamespace(nChildAnnotations=len(children))
            self.page = SimpleNamespace(_children=lambda handle, count: iter(children))
    memo = Node(A.STICKY, [Node(A.TEXT), Node(A.STICKY, [Node(A.TEXT)])])
    assert ReviewSdk._sticky_subtrees(memo) == 2
    assert ReviewSdk._sticky_subtrees(Node(A.TEXT)) == 0
    assert ReviewSdk._sticky_subtrees(Node(A.RECTANGLE, [memo])) == 2
    with pytest.raises(ValueError, match='outside a sticky'):
        ReviewSdk._sticky_subtrees(Node(A.RECTANGLE, [memo, Node(A.TEXT)]))


@pytest.mark.parametrize('empty', [False, True])
def test_new_schemas_and_jsonl(tmp_path, monkeypatch, empty):
    import jsonschema
    _, session, _ = modern(tmp_path, monkeypatch, empty=empty)
    result = take(session, tmp_path/'result')
    for filename, schema in [('reviewed.json','reviewed-result'), ('manifest.json','reviewed-result-manifest')]:
        definition = read(Path(m.__file__).with_name(schema+'-2.0.schema.json'))
        jsonschema.Draft202012Validator.check_schema(definition)
        jsonschema.validate(read(result.root/filename), definition, format_checker=jsonschema.FormatChecker())
    definition = read(Path(m.__file__).with_name('reviewed-text-2.0.schema.json'))
    for line in (result.root/'reviewed.jsonl').read_text(encoding='utf-8').splitlines():
        jsonschema.validate(json.loads(line), definition)
    definition = read(Path(m.__file__).with_name('reviewed-origins-2.0.schema.json'))
    jsonschema.validate(payload(session), definition)
