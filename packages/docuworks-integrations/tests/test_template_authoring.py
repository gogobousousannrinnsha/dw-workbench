"""Authoring contracts with fake native I/O and real saved-result validation."""
import copy
import json
from pathlib import Path
import shutil

import pytest

from docuworks_integrations import template_authoring as a, templates as t
from docuworks_integrations import reviewed as r
from docuworks_integrations.structured import apply_rectangle_template
from test_reviewed import read, write, hashes
from test_reviewed_v2 import modern, take


class Sdk:
    def seed(self, path, definition):
        raw = read(path)
        for page, source in zip(raw['pages'], definition['pages']):
            page['rectangles'] = []
            for rect in source['rectangles']:
                attrs = dict(項目名=dict(kind='STRING', value=rect['name']),
                             用途=dict(kind='STRING', value='取得' if rect['purpose'] == 'field' else '適用判定'))
                if rect['expected'] is not None: attrs['期待文字'] = dict(kind='STRING', value=rect['expected'])
                page['rectangles'].append(dict(rect, uid=None, attributes=attrs))
        write(path, raw)

    def inspect(self, path):
        raw = read(path)
        body = copy.deepcopy(raw)
        for page in body['pages']: page.pop('rectangles', None)
        pages = []
        for page in raw['pages']:
            pages.append({**{k: page[k] for k in ('page','width_mm','height_mm','rotation')},
                          'rectangles': copy.deepcopy(page.get('rectangles', []))})
        return dict(pages=pages, body_sha256=r._digest(r._bytes(body)))

    def write(self, path, pages, settings=None):
        raw = read(path)
        for page in pages:
            for rect in page['rectangles']:
                actual = next(x for x in raw['pages'][page['page'] - 1]['rectangles']
                              if x['annotation_order'] == rect['annotation_order'])
                actual['uid'] = rect['uid']
                if settings is not None:
                    s = settings[rect['uid']]
                    actual['attributes'] = dict(用途=dict(kind='STRING', value=s['purpose']),
                        項目名=dict(kind='STRING', value=s['name']), 結合方法=dict(kind='STRING', value=s['join']))
                    if s['purpose'] == '適用判定':
                        actual['attributes']['期待文字'] = dict(kind='STRING', value=s['expected'])
                    else:
                        actual['attributes'].update(必須=dict(kind='BOOL', value=s['required']),
                                                     出力順=dict(kind='INT', value=s['order']))
        write(path, raw)


def environment(tmp_path, monkeypatch):
    run, session, _ = modern(tmp_path, monkeypatch)
    result = take(session, tmp_path/'reviewed')
    app = tmp_path/'アプリ 空白'; app.mkdir()
    sdk = Sdk()
    monkeypatch.setattr(a, '_sdk', lambda dll=None: sdk)
    monkeypatch.setattr(t, '_sdk', lambda dll=None: sdk)
    draft = a.create_template_draft(app, result.root, name='帳簿A')
    return app, draft, result, sdk


def add_rect(draft, *, uid=None, name=None):
    raw = read(draft.working_xdw)
    page = raw['pages'][0]
    text = page['items'][0]
    attrs = {} if name is None else {'項目名': dict(kind='STRING', value=name)}
    rectangles = page.setdefault('rectangles', [])
    x, y = max(0, text['x'] - 1), max(0, text['y'] - 1)
    rectangles.append(dict(annotation_order=len(page['items']) + len(rectangles) + 1,
                           x=x, y=y, width=min(text['width'] + 2, page['width_mm'] - x),
                           height=min(text['height'] + 2, page['height_mm'] - y), uid=uid, attributes=attrs))
    write(draft.working_xdw, raw)
    return a.refresh_template_draft(draft.root, expected_revision=draft.revision)


def configure(draft, **values):
    settings = draft.data['settings']; uid = next(iter(settings))
    settings[uid].update(name='部品番号', **values)
    return a.update_template_draft(draft.root, settings=settings, expected_revision=draft.revision)


def test_create_edit_publish_revise_and_move_without_originals(tmp_path, monkeypatch):
    app, draft, original, sdk = environment(tmp_path, monkeypatch)
    before = hashes(original.root)
    draft = configure(add_rect(draft))
    preview = a.preview_template_draft(draft.root)
    with pytest.raises(ValueError, match='確認事項'):
        a.publish_template_draft(draft.root, app, expected_revision=draft.revision)
    template = a.publish_template_draft(draft.root, app, expected_revision=draft.revision, confirm_warnings=True)
    assert template.root == app/'templates/帳簿A/v001'
    assert hashes(original.root) == before
    actual = apply_rectangle_template(template.root, original.root, tmp_path/'structured')
    assert [(f['name'], f['value']) for f in actual.data['fields']] == [
        (f['name'], f['value']) for f in preview['fields']]
    moved = tmp_path/'移動先'; moved.mkdir()
    shutil.move(app/'templates', moved/'templates')
    shutil.rmtree(original.root)
    revised = a.create_template_draft(moved, base_template_dir=moved/'templates/帳簿A/v001')
    assert revised.data['settings'] == draft.data['settings']
    previous = hashes(moved/'templates/帳簿A/v001')
    v2 = a.publish_template_draft(revised.root, moved, expected_revision=revised.revision, confirm_warnings=True)
    assert v2.root.name == 'v002'
    assert hashes(moved/'templates/帳簿A/v001') == previous


def test_incomplete_autosave_and_stale_editor_are_separate(tmp_path, monkeypatch):
    app, draft, *_ = environment(tmp_path, monkeypatch)
    draft = add_rect(draft)
    saved = a.update_template_draft(draft.root, settings=draft.data['settings'],
                                     name='', expected_revision=draft.revision)
    assert a.load_template_draft(saved.root).data['name'] == ''
    with pytest.raises(ValueError): a.preview_template_draft(saved.root)
    with pytest.raises(RuntimeError, match='更新'):
        a.update_template_draft(draft.root, settings=draft.data['settings'], expected_revision=draft.revision)


def test_rectangle_movement_preserves_names_but_clones_do_not_guess(tmp_path, monkeypatch):
    _, draft, *_ = environment(tmp_path, monkeypatch)
    draft = configure(add_rect(draft)); settings = draft.data['settings']
    raw = read(draft.working_xdw); raw['pages'][0]['rectangles'][0]['x'] += 2
    write(draft.working_xdw, raw)
    with pytest.raises(ValueError, match='再読込'): a.preview_template_draft(draft.root)
    draft = a.refresh_template_draft(draft.root)
    assert draft.data['settings'] == settings
    draft = add_rect(draft, uid=next(iter(settings)))
    assert all(not s['name'] for s in draft.data['settings'].values())
    assert len(draft.data['settings']) == 2 and draft.data['notices']
    assert not set(settings) & set(draft.data['settings'])


@pytest.mark.parametrize('change', ['text','x','width_mm','rotation'])
def test_body_and_page_changes_rejected_without_losing_last_snapshot(tmp_path, monkeypatch, change):
    _, draft, *_ = environment(tmp_path, monkeypatch)
    draft = configure(add_rect(draft)); old = (draft.root/'draft.json').read_bytes()
    raw = read(draft.working_xdw)
    if change == 'text': raw['pages'][0]['items'][0]['text'] = 'changed'
    elif change == 'x': raw['pages'][0]['items'][0]['x'] += 1
    else: raw['pages'][0][change] += 1
    write(draft.working_xdw, raw)
    with pytest.raises(ValueError, match='再取り込み'): a.refresh_template_draft(draft.root)
    assert (draft.root/'draft.json').read_bytes() == old


def test_conditions_block_registration_but_missing_values_can_be_confirmed(tmp_path, monkeypatch):
    app, draft, *_ = environment(tmp_path, monkeypatch)
    draft = configure(add_rect(draft))
    draft = add_rect(draft)
    settings = draft.data['settings']; uid = list(settings)[1]
    settings[uid].update(name='判定', purpose='適用判定', expected='wrong')
    draft = a.update_template_draft(draft.root, settings=settings, expected_revision=draft.revision)
    assert not a.preview_template_draft(draft.root)['applicable']
    with pytest.raises(ValueError, match='条件'):
        a.publish_template_draft(draft.root, app, expected_revision=draft.revision, confirm_warnings=True)
    assert not (app/'templates/帳簿A').exists()


@pytest.mark.parametrize('file', ['authoring/state.json','authoring/sample-reviewed/reviewed.json','source-template.xdw'])
def test_published_context_corruption_cannot_be_used_for_revision(tmp_path, monkeypatch, file):
    app, draft, *_ = environment(tmp_path, monkeypatch)
    draft = configure(add_rect(draft))
    result = a.publish_template_draft(draft.root, app, expected_revision=draft.revision, confirm_warnings=True)
    (result.root/file).write_bytes(b'broken')
    with pytest.raises((ValueError, RuntimeError)):
        a.create_template_draft(app, base_template_dir=result.root)


def test_failed_final_journal_does_not_duplicate_a_completed_version(tmp_path, monkeypatch):
    app, draft, *_ = environment(tmp_path, monkeypatch)
    draft = configure(add_rect(draft))
    original = a._commit
    def fail(folder, data):
        if data.get('registered'): raise OSError('sharing violation')
        return original(folder, data)
    monkeypatch.setattr(a, '_commit', fail)
    first = a.publish_template_draft(draft.root, app, expected_revision=draft.revision, confirm_warnings=True)
    second = a.publish_template_draft(draft.root, app, expected_revision=draft.revision, confirm_warnings=True)
    assert first.template_id == second.template_id
    assert not (app/'templates/帳簿A/v002').exists()


def test_registration_failure_keeps_draft_and_has_no_visible_version(tmp_path, monkeypatch):
    app, draft, _, sdk = environment(tmp_path, monkeypatch)
    draft = configure(add_rect(draft))
    original_write = sdk.write
    def fail(*args, **kwargs): raise OSError('native save failure')
    monkeypatch.setattr(sdk, 'write', fail)
    with pytest.raises(OSError):
        a.publish_template_draft(draft.root, app, expected_revision=draft.revision, confirm_warnings=True)
    assert a.list_template_versions(app) == []
    assert a.load_template_draft(draft.root).data['settings'] == draft.data['settings']
    monkeypatch.setattr(sdk, 'write', original_write)
    assert a.publish_template_draft(draft.root, app, expected_revision=draft.revision, confirm_warnings=True).root.name == 'v001'


def test_required_missing_is_visible_and_requires_confirmation(tmp_path, monkeypatch):
    app, draft, *_ = environment(tmp_path, monkeypatch)
    draft = configure(add_rect(draft))
    raw = read(draft.working_xdw)
    raw['pages'][0]['rectangles'][0].update(x=0, y=0, width=1, height=1)
    write(draft.working_xdw, raw)
    draft = a.refresh_template_draft(draft.root)
    preview = a.preview_template_draft(draft.root)
    assert preview['fields'][0]['status'] == 'missing' and preview['warnings']
    with pytest.raises(ValueError, match='確認事項'):
        a.publish_template_draft(draft.root, app, expected_revision=draft.revision)
    assert a.publish_template_draft(draft.root, app, expected_revision=draft.revision, confirm_warnings=True)


def test_legacy_flat_template_stays_immutable_and_revisions_visible(tmp_path, monkeypatch):
    app, draft, reviewed, *_ = environment(tmp_path, monkeypatch)
    draft = configure(add_rect(draft))
    created = a.publish_template_draft(draft.root, app, expected_revision=draft.revision, confirm_warnings=True)
    other = tmp_path/'legacy-app'; (other/'templates').mkdir(parents=True)
    legacy = t.register_rectangle_template(created.root/'source-template.xdw', other/'templates/帳簿A', name='帳簿A')
    before = hashes(legacy.root)
    revised = a.create_template_draft(other, reviewed.root, base_template_dir=legacy.root)
    new = a.publish_template_draft(revised.root, other, expected_revision=revised.revision, confirm_warnings=True)
    assert new.root == other/'templates/帳簿A-versions/v001'
    assert hashes(legacy.root) == before and len(a.list_template_versions(other)) == 2
    next_draft = a.create_template_draft(other, base_template_dir=new.root)
    new2 = a.publish_template_draft(next_draft.root, other, expected_revision=next_draft.revision, confirm_warnings=True)
    assert new2.root == other/'templates/帳簿A-versions/v002'


@pytest.mark.parametrize('name', ['../帳簿','帳簿/別','CON','a.',' a','.hidden'])
def test_family_names_cannot_escape_or_hide_storage(name):
    with pytest.raises(ValueError): a.family_name(name)


def test_same_draft_lock_is_nonblocking(tmp_path):
    from docuworks_integrations._authoring_storage import locked
    with locked(tmp_path):
        with pytest.raises(RuntimeError, match='使用中'):
            with locked(tmp_path): pass
