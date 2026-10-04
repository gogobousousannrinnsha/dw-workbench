"""Local template authoring. Published templates keep the existing 1.0 contract.

Draft JSON is mutable and permits incomplete labels. Samples and inspected
generations are immutable; compare-and-swap revisions reject stale editors.
"""
from collections import Counter
import copy
from dataclasses import dataclass
import os
from pathlib import Path
import re
import uuid

from . import reviewed as r, templates as t
from ._authoring_storage import atomic_write, copy_reviewed, locked, read
from ._storage import owned_directory, publish_new
from ._template_extract import evaluate, _extract

DRAFT_SCHEMA = 'docuworks-template-draft'
AUTHORING_SCHEMA = 'docuworks-template-authoring'
SETTING_KEYS = {'name', 'purpose', 'expected', 'required', 'join', 'order'}


def _sdk(dll_path=None):
    from ._template_authoring_sdk import AuthoringSdk
    return AuthoringSdk(dll_path)


def family_name(name):
    if (not isinstance(name, str) or not name.strip() or name != name.strip() or
            name.endswith('.') or name.startswith('.') or any(ord(c) < 32 or c in '<>:"/\\|?*' for c in name) or
            name in ('.', '..') or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', name, re.I)):
        raise ValueError('テンプレート名にはWindowsのフォルダー名として使える名前を入力してください。')
    return name


def _workspace(app_root):
    root = r._plain_path(app_root)
    if not root.is_dir():
        raise FileNotFoundError(root)
    # Reject workspaces nested in an immutable result, before creating children.
    r._destination(root / ('.authoring-check-' + uuid.uuid4().hex))
    for name in ('templates', 'template-drafts'):
        r._plain_path(root / name).mkdir(exist_ok=True)
    return root


def _default(order=1):
    return dict(name='', purpose='取得', expected='', required=True, join='連結', order=order)


def _settings_valid(settings):
    if not isinstance(settings, dict):
        raise ValueError('下書きの設定が不正です。')
    for uid, setting in settings.items():
        r._uuid(uid)
        if not isinstance(setting, dict) or set(setting) != SETTING_KEYS:
            raise ValueError('下書きの項目設定が不正です。')
        if any(not isinstance(setting[k], str) for k in ('name', 'purpose', 'expected', 'join')):
            raise ValueError('項目名・期待文字は文字列で指定してください。')
        if setting['purpose'] not in t.PURPOSES or setting['join'] not in t.JOINS:
            raise ValueError('用途・結合方法が不正です。')
        if type(setting['required']) is not bool:
            raise ValueError('必須の設定が不正です。')
        r._integer(setting['order'], 1, 2**31 - 1)


def _rectangles(snapshot):
    return [rect for page in snapshot['pages'] for rect in page['rectangles']]


def _geometry(snapshot):
    return [[{k: rect[k] for k in ('annotation_order', 'x', 'y', 'width', 'height', 'uid')}
             for rect in page['rectangles']] for page in snapshot['pages']]


@dataclass(frozen=True)
class TemplateDraft:
    root: Path
    _bytes: bytes

    @property
    def data(self):
        import json
        return json.loads(self._bytes)

    @property
    def working_xdw(self): return self.root / 'working.xdw'

    @property
    def revision(self): return self.data['revision']


def _load(folder):
    folder = r._plain_path(folder)
    data = read(folder / 'draft.json')
    if data.get('schema') != DRAFT_SCHEMA or data.get('schema_version') != '1.0':
        raise ValueError('対応していない下書きです。')
    r._uuid(data['draft_id']); r._integer(data['revision'], 0, 2**31 - 1)
    if data['draft_id'] != folder.name:
        raise ValueError('下書きの識別情報が一致しません。')
    if not isinstance(data['name'], str): raise ValueError('下書き名が不正です。')
    _settings_valid(data['settings'])
    sample = r.load_reviewed_result(folder / 'sample-reviewed')
    if sample.manifest_sha256 != data['sample_manifest_sha256']:
        raise RuntimeError('保存した見本が変更されています。')
    r._hash(data['body_sha256'])
    if data['generation'] is not None:
        r._uuid(data['generation'])
        generation = folder / 'snapshots' / data['generation']
        for file, key in (('snapshot.json', 'snapshot_sha256'), ('source.xdw', 'work_sha256')):
            if r.sha256(r._plain_path(generation / file)) != data[key]:
                raise RuntimeError('保存した矩形の読み取り結果が変更されています。')
        snapshot = read(generation / 'snapshot.json')
        uids = [rect['uid'] for rect in _rectangles(snapshot)]
        if len(uids) != len(set(uids)) or set(uids) != set(data['settings']):
            raise ValueError('矩形と項目設定の対応が一致しません。')
    r._plain_path(folder / 'working.xdw')
    return TemplateDraft(folder, r._bytes(data))


def load_template_draft(draft_dir):
    """Read and verify the last saved state, without loading Tk, Pillow or SDK."""
    return _load(draft_dir)


def _current(folder, expected_revision):
    draft = _load(folder)
    if expected_revision is not None and draft.revision != expected_revision:
        raise RuntimeError('下書きが別の操作で更新されています。再度開いてください。')
    if draft.data.get('registered'):
        raise ValueError('登録済みの下書きです。登録版から改訂してください。')
    return draft


def _commit(folder, data):
    data['revision'] += 1
    atomic_write(folder / 'draft.json', data)
    return _load(folder)


def load_authoring_context(template_dir):
    """Optional, separately hashed sample/settings attached to a 1.0 template."""
    template = t.load_rectangle_template(template_dir)
    folder = template.root / 'authoring'
    if not folder.exists():
        return None
    manifest = read(folder / 'manifest.json')
    if (manifest.get('schema') != AUTHORING_SCHEMA or manifest.get('schema_version') != '1.0'
            or manifest.get('status') != 'COMPLETE'):
        raise ValueError('作成用見本の保存情報が不正です。')
    if manifest['template_manifest_sha256'] != template.manifest_sha256:
        raise ValueError('テンプレートと作成用見本の組み合わせが異なります。')
    sample = r.load_reviewed_result(folder / 'sample-reviewed')
    sample_manifest = read(sample.root / 'manifest.json')
    names = {'state.json', 'sample-reviewed/manifest.json'} | {
        'sample-reviewed/' + name for name in sample_manifest['files']}
    if set(manifest['files']) != names:
        raise ValueError('作成用見本のファイル一覧が不正です。')
    for name, digest in manifest['files'].items():
        if r.sha256(r._plain_path(folder / name)) != digest:
            raise RuntimeError('作成用見本・設定が変更されています。')
    state = read(folder / 'state.json')
    _settings_valid(state['settings'])
    if state['sample_manifest_sha256'] != sample.manifest_sha256:
        raise ValueError('作成用見本が一致しません。')
    return dict(sample_dir=sample.root, state=state)


def create_template_draft(app_root, reviewed_dir=None, *, name=None, base_template_dir=None, dll_path=None):
    root = _workspace(app_root)
    base = t.load_rectangle_template(base_template_dir) if base_template_dir else None
    context = load_authoring_context(base.root) if base else None
    if context is not None:
        if reviewed_dir is not None:
            raise ValueError('改訂では保存済みの見本を使用します。別の見本は新規作成で指定してください。')
        reviewed_dir = context['sample_dir']
    if reviewed_dir is None:
        raise ValueError('見本のReviewed保存フォルダーを選択してください。')
    sample = r.load_reviewed_result(reviewed_dir)
    name = family_name(name if name is not None else base.data['name'] if base else '')
    if base and base.data['name'] != name:
        raise ValueError('改訂では元のテンプレート名を使用してください。')
    if not base and (root / 'templates' / name).exists():
        raise FileExistsError('同じ名前が登録済みです。「登録済みから改訂」を選んでください。')
    if any(p['rotation'] != 0 for p in sample.pages):
        raise ValueError('回転したページはテンプレート作成に対応していません。')
    identity = str(uuid.uuid4())
    output = root / 'template-drafts' / identity
    sdk = _sdk(dll_path)
    with owned_directory(output.parent, '.authoring-new-') as staging:
        copied = copy_reviewed(sample.root, staging / 'sample-reviewed')
        baseline = sdk.inspect(copied.root / 'source-review.xdw')
        r._copy(base.root / 'source-template.xdw' if context else copied.root / 'source-review.xdw',
                staging / 'working.xdw')
        if base and context is None:
            if [(p['width_mm'], p['height_mm'], p['rotation']) for p in base.data['pages']] != [
                    (p['width_mm'], p['height_mm'], p['rotation']) for p in sample.pages]:
                raise ValueError('見本とテンプレートのページ情報が一致しません。')
            sdk.seed(staging / 'working.xdw', base.data)
        state = dict(schema=DRAFT_SCHEMA, schema_version='1.0', draft_id=identity, name=name, revision=0,
                     sample_manifest_sha256=copied.manifest_sha256, body_sha256=baseline['body_sha256'],
                     base_template_id=base.template_id if base else None,
                     generation=None, settings={}, registered=None, notices=[], created_at=r._now())
        (staging / 'draft.json').write_bytes(r._bytes(state))
        (staging / 'snapshots').mkdir()
        publish_new(staging, output)
    # A failed first inspection leaves a recoverable draft, never a template.
    return refresh_template_draft(output, expected_revision=0, dll_path=dll_path,
                                  initial_settings=context['state']['settings'] if context else None,
                                  adopt_attributes=base is not None and context is None)


def refresh_template_draft(draft_dir, *, expected_revision=None, dll_path=None,
                           initial_settings=None, adopt_attributes=False):
    folder = r._plain_path(draft_dir)
    with locked(folder):
        draft = _current(folder, expected_revision)
        data = draft.data
        sdk = _sdk(dll_path)
        with owned_directory(folder, '.authoring-read-') as stage:
            before = r._copy(draft.working_xdw, stage / 'source.xdw')
            snapshot = sdk.inspect(stage / 'source.xdw')
            if snapshot['body_sha256'] != data['body_sha256']:
                raise ValueError('見本の文字・位置・ページが変更されています。校正結果を再取り込みして新規作成してください。')
            old = data['settings'] if initial_settings is None else initial_settings
            counts = Counter(rect.get('uid') for rect in _rectangles(snapshot))
            settings = {}; notices = []
            for index, rect in enumerate(_rectangles(snapshot), 1):
                uid = rect.get('uid')
                retained = uid is not None and counts[uid] == 1 and uid in old
                setting = copy.deepcopy(old[uid]) if retained else _default(index)
                if not retained:
                    if uid is not None and counts[uid] > 1:
                        notices.append('複製された矩形は項目名を再設定してください。')
                    uid = str(uuid.uuid4())
                    if adopt_attributes:
                        attrs = rect['attributes']
                        for key, label in [('name','項目名'),('purpose','用途'),('expected','期待文字'),
                                           ('required','必須'),('join','結合方法'),('order','出力順')]:
                            if label in attrs:
                                setting[key] = attrs[label]['value']
                rect['uid'] = uid; settings[uid] = setting
            if set(old) - set(settings):
                notices.append('削除・描き直しで対応しなくなった項目があります。範囲一覧を確認してください。')
            _settings_valid(settings)
            sdk.write(stage / 'source.xdw', snapshot['pages'])
            reopened = sdk.inspect(stage / 'source.xdw')
            if reopened['body_sha256'] != data['body_sha256'] or _geometry(reopened) != _geometry(snapshot):
                raise RuntimeError('矩形識別情報の保存・再読込が一致しません。')
            (stage / 'snapshot.json').write_bytes(r._bytes(reopened))
            generation = str(uuid.uuid4())
            dest = folder / 'snapshots' / generation
            publish_new(stage, dest)
        if r.sha256(draft.working_xdw) != before:
            raise RuntimeError('読込中にXDWが変更されました。Viewerを閉じて再読込してください。')
        # Replace only an owned editable copy. A sharing violation leaves the
        # previous draft state intact and the new generation available for diagnosis.
        replacement = folder / ('.authoring-work-' + uuid.uuid4().hex + '.xdw')
        try:
            r._copy(dest / 'source.xdw', replacement)
            if r.sha256(draft.working_xdw) != before:
                raise RuntimeError('作業XDWが変更されました。再読込してください。')
            os.replace(replacement, draft.working_xdw)
        finally:
            replacement.unlink(missing_ok=True)
        data.update(generation=generation, work_sha256=r.sha256(dest / 'source.xdw'),
                    snapshot_sha256=r.sha256(dest / 'snapshot.json'), settings=settings,
                    notices=list(dict.fromkeys(notices)))
        return _commit(folder, data)


def update_template_draft(draft_dir, *, settings, expected_revision, name=None):
    folder = r._plain_path(draft_dir)
    with locked(folder):
        draft = _current(folder, expected_revision)
        data = draft.data
        _settings_valid(settings)
        if set(settings) != set(data['settings']):
            raise ValueError('設定する矩形が一致しません。再読込してください。')
        if name is not None:
            if not isinstance(name, str): raise ValueError('テンプレート名は文字列で指定してください。')
            if data['base_template_id'] and name != data['name']:
                raise ValueError('改訂ではテンプレート名を変更できません。')
            data['name'] = name
        data['settings'] = copy.deepcopy(settings)
        return _commit(folder, data)


def _snapshot(draft, *, fresh=True):
    data = draft.data
    if data['generation'] is None:
        raise ValueError('Viewerを保存して閉じ、矩形を再読込してください。')
    if fresh and r.sha256(draft.working_xdw) != data['work_sha256']:
        raise ValueError('ViewerでXDWが変更されています。「再読込」を実行してください。')
    return read(draft.root / 'snapshots' / data['generation'] / 'snapshot.json')


def _definition(draft):
    data = draft.data
    family_name(data['name'])
    snapshot = _snapshot(draft)
    for rect in _rectangles(snapshot):
        setting = data['settings'][rect['uid']]
        attrs = dict(用途=dict(kind='STRING', value=setting['purpose']),
                     項目名=dict(kind='STRING', value=setting['name']),
                     結合方法=dict(kind='STRING', value=setting['join']))
        if setting['purpose'] == '適用判定':
            attrs['期待文字'] = dict(kind='STRING', value=setting['expected'])
        else:
            attrs.update(必須=dict(kind='BOOL', value=setting['required']),
                         出力順=dict(kind='INT', value=setting['order']))
        rect['attributes'] = attrs
    return t._compile(snapshot, data['name'], data['work_sha256'])


def _preview(draft):
    result = evaluate(_definition(draft), r.load_reviewed_result(draft.root / 'sample-reviewed').data)
    result['warnings'] = bool(result['diagnostics'] or any(
        row['diagnostics'] for row in result['fields'] + result['conditions']))
    return result


def preview_template_draft(draft_dir):
    folder = r._plain_path(draft_dir)
    with locked(folder):
        return _preview(_current(folder, None))


def rectangle_examples(draft_dir):
    """Individual examples also work before field names/conditions are complete."""
    draft = _load(draft_dir)
    snapshot = _snapshot(draft)
    sample = r.load_reviewed_result(draft.root / 'sample-reviewed').data
    rows = {}
    for page in snapshot['pages']:
        for rect in page['rectangles']:
            setting = draft.data['settings'][rect['uid']]
            definition = dict(rect, rectangle_id=rect['uid'], name=setting['name'],
                              purpose='field', required=setting['required'], join=setting['join'])
            rows[rect['uid']] = _extract(definition, sample['pages'][page['page'] - 1], sample)
    return rows


def render_template_page(draft_dir, page, *, dll_path=None):
    folder = r._plain_path(draft_dir)
    with locked(folder):
        draft = _load(folder)
        sample = r.load_reviewed_result(folder / 'sample-reviewed')
        r._integer(page, 1, len(sample.pages))
        cache = folder / 'previews'; r._plain_path(cache).mkdir(exist_ok=True)
        target = cache / f'page-{page:04d}'
        if not target.exists():
            with owned_directory(cache, '.render-') as stage:
                metadata = _sdk(dll_path).render(sample.root / 'source-review.xdw', page, stage)
                (stage / 'image.json').write_bytes(r._bytes(metadata))
                publish_new(stage, target)
        return dict(path=str(r._plain_path(target / 'image.png')), **read(target / 'image.json'))


def _comparison(definition):
    return {key: value for key, value in definition.items()
            if key not in ('template_id', 'created_at', 'source_xdw_sha256')}


def _version_family(root, data):
    """Keep revisions together, including legacy flat template directories."""
    if data['base_template_id']:
        for row in list_template_versions(root):
            path = Path(row['path'])
            if (not row['error'] and row['template_id'] == data['base_template_id']
                    and path.parent.parent == root / 'templates'):
                return r._plain_path(path.parent)
    family = r._plain_path(root / 'templates' / family_name(data['name']))
    if data['base_template_id'] and (family / 'manifest.json').exists():
        # A flat legacy bundle is immutable. Create a sibling version family.
        family = r._plain_path(family.with_name(family.name + '-versions'))
        if (family / 'manifest.json').exists():
            raise FileExistsError('改訂用の保存先が既存テンプレートと重なります。保存フォルダーを確認してください。')
        if family.exists():
            for row in list_template_versions(root):
                if Path(row['path']).parent == family and (row['error'] or row['name'] != data['name']):
                    raise FileExistsError('改訂用の保存先に別のテンプレートがあります。')
    return family


def publish_template_draft(draft_dir, app_root, *, expected_revision, confirm_warnings=False, dll_path=None):
    root = _workspace(app_root)
    folder = r._plain_path(draft_dir)
    if folder.parent != root / 'template-drafts':
        raise ValueError('このPortableの下書きを指定してください。')
    with locked(folder), locked(root / 'templates'):
        saved = _load(folder)
        if expected_revision != saved.revision:
            raise RuntimeError('下書きが更新されています。再度開いてください。')
        # A version rename may succeed immediately before the process stops or
        # its draft journal fails. Reconcile that success before doing any work.
        for row in list_template_versions(root):
            if row['error'] or not row['has_sample']: continue
            context = load_authoring_context(row['path'])
            if context['state']['draft_id'] == saved.data['draft_id']:
                if context['state']['settings'] != saved.data['settings'] or row['name'] != saved.data['name']:
                    raise ValueError('この下書きは登録済みです。登録版から改訂してください。')
                recovered = saved.data
                recovered['registered'] = Path(row['path']).relative_to(root).as_posix()
                try: _commit(folder, recovered)
                except OSError: pass
                return t.load_rectangle_template(row['path'])
        draft = _current(folder, expected_revision)
        data = draft.data
        expected = _definition(draft)
        preview = _preview(draft)
        if not preview['applicable']:
            raise ValueError('見本と適用条件が一致しません。設定を修正してください。')
        if preview['warnings'] and not confirm_warnings:
            raise ValueError('確認事項があります。内容を確認してから登録してください。')
        family = _version_family(root, data)
        if family.exists() and data['base_template_id'] is None:
            raise FileExistsError('同名のテンプレートが登録済みです。改訂として作成してください。')
        versions = [int(p.name[1:]) for p in family.iterdir() if re.fullmatch(r'v\d{3,}', p.name)] if family.exists() else []
        output = family / f'v{max(versions, default=0) + 1:03d}'
        # Keep native temporary paths short and do not reserve the family name
        # until the complete version is ready. A failed save remains retryable.
        with owned_directory(root / 'templates', '.publish-') as stage:
            source = stage / 'assigned.xdw'
            r._copy(folder / 'snapshots' / data['generation'] / 'source.xdw', source)
            sdk = _sdk(dll_path)
            snapshot = _snapshot(draft)
            sdk.write(source, snapshot['pages'], data['settings'])
            check = sdk.inspect(source)
            if check['body_sha256'] != data['body_sha256'] or _geometry(check) != _geometry(snapshot):
                raise RuntimeError('属性設定後の文字・位置・矩形が一致しません。')
            registered = t.register_rectangle_template(source, stage / 'complete', name=data['name'], dll_path=dll_path)
            if _comparison(registered.data) != _comparison(expected):
                raise RuntimeError('画面の設定と登録結果が一致しません。')
            authoring = registered.root / 'authoring'; authoring.mkdir()
            sample = copy_reviewed(folder / 'sample-reviewed', authoring / 'sample-reviewed')
            state = dict(settings=data['settings'], sample_manifest_sha256=sample.manifest_sha256,
                         body_sha256=data['body_sha256'], draft_id=data['draft_id'],
                         parent_template_id=data['base_template_id'])
            (authoring / 'state.json').write_bytes(r._bytes(state))
            files = {p.relative_to(authoring).as_posix(): r.sha256(p) for p in authoring.rglob('*') if p.is_file()}
            (authoring / 'manifest.json').write_bytes(r._bytes(dict(schema=AUTHORING_SCHEMA, schema_version='1.0',
                status='COMPLETE', template_manifest_sha256=registered.manifest_sha256, files=files)))
            load_authoring_context(registered.root)
            _load(folder); _snapshot(draft)  # detect input changes before finalization
            created_family = not family.exists()
            family.mkdir(exist_ok=True)
            try:
                publish_new(registered.root, output)
            except BaseException:
                if created_family:
                    try: family.rmdir()  # only the empty directory created here
                    except OSError: pass
                raise
        data['registered'] = output.relative_to(root).as_posix()
        try:
            _commit(folder, data)
        except OSError:
            # The version is already complete. Discovery by draft_id below makes
            # a later retry idempotent even if the final journal write fails.
            pass
        return t.load_rectangle_template(output)


def list_template_versions(app_root):
    root = r._plain_path(app_root) / 'templates'
    if not root.exists(): return []
    rows = []
    for family in sorted(root.iterdir()):
        if family.name.startswith('.') or not family.is_dir(): continue
        candidates = [family] if (family / 'template.json').is_file() else [
            p for p in sorted(family.iterdir()) if re.fullmatch(r'v\d{3,}', p.name) and p.is_dir()]
        for path in candidates:
            try:
                item = t.load_rectangle_template(path)
                context = load_authoring_context(path)
                rows.append(dict(path=str(path), name=item.data['name'], template_id=item.template_id,
                                 version=path.name, has_sample=context is not None, error=None))
            except Exception as exc:
                rows.append(dict(path=str(path), name=family.name, version=path.name, error=str(exc), has_sample=False))
    return rows
