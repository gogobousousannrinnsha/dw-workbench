"""Immutable rectangle templates. Saved definitions need no native dependencies."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
import uuid

from . import reviewed as r

SCHEMA = 'docuworks-rectangle-template'
VERSION = '1.0'
FILES = {'template.json', 'source-template.xdw'}
ATTRIBUTE_NAMES = {'用途', '項目名', '期待文字', '必須', '出力順', '結合方法'}
PURPOSES = {'取得': 'field', '適用判定': 'condition'}
JOINS = {'連結': '', '空白': ' ', '改行': '\n'}


def hundredths(value):
    """Compare SDK page dimensions at 0.01 mm, with decimal half-up rounding."""
    r._number(value)
    return int((Decimal(str(value)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def _name(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('名前は空でない文字列を指定してください。')
    return value


def _attribute(attrs, name, kind, default=None, *, required=False):
    if name not in attrs:
        if required:
            raise ValueError(f'矩形の属性「{name}」がありません。')
        return default
    actual = attrs[name]
    if actual['kind'] != kind:
        raise ValueError(f'矩形の属性「{name}」の種類が不正です（{kind}）。')
    return actual['value']


def _compile(snapshot, name, source_hash):
    pages = []
    for page in snapshot['pages']:
        target = {key: page[key] for key in ('page', 'width_mm', 'height_mm', 'rotation')}
        target['rectangles'] = []
        for rect in page['rectangles']:
            attrs = rect['attributes']
            purpose = _attribute(attrs, '用途', 'STRING', required=True)
            join = _attribute(attrs, '結合方法', 'STRING', '連結')
            if purpose not in PURPOSES or join not in JOINS:
                raise ValueError('矩形の用途または結合方法が不正です。')
            field_name = _name(_attribute(attrs, '項目名', 'STRING', required=True))
            expected = _attribute(attrs, '期待文字', 'STRING', required=purpose == '適用判定')
            required = _attribute(attrs, '必須', 'BOOL', True)
            order = _attribute(attrs, '出力順', 'INT')
            if purpose == '取得' and expected is not None:
                raise ValueError('期待文字は適用判定用の矩形に設定してください。')
            if purpose == '適用判定' and any(k in attrs for k in ('必須', '出力順')):
                raise ValueError('必須・出力順は取得用の矩形に設定してください。')
            entry = {key: rect[key] for key in ('annotation_order', 'x', 'y', 'width', 'height')}
            entry.update(rectangle_id=f'p{page["page"]:04d}-a{rect["annotation_order"]:06d}',
                         purpose=PURPOSES[purpose], name=field_name, expected=expected,
                         required=required, output_order=order, join=join)
            target['rectangles'].append(entry)
        pages.append(target)
    data = dict(schema=SCHEMA, schema_version=VERSION, template_id=str(uuid.uuid4()), name=name,
                created_at=r._now(), source_xdw_sha256=source_hash, coordinate_basis='reviewed',
                coordinate_system=r.COORDINATES, unit='mm', pages=pages)
    validate_template(data)
    return data


def validate_template(data):
    r._keys(data, 'schema schema_version template_id name created_at source_xdw_sha256 coordinate_basis coordinate_system unit pages')
    r._header(data, SCHEMA); r._uuid(data['template_id']); r._timestamp(data['created_at'])
    r._hash(data['source_xdw_sha256']); _name(data['name'])
    if (data['coordinate_basis'] != 'reviewed' or data['coordinate_system'] != r.COORDINATES or data['unit'] != 'mm'):
        raise ValueError('テンプレートの座標系が不正です。')
    if not isinstance(data['pages'], list) or not data['pages']:
        raise ValueError('テンプレートにはページが必要です。')
    names, fields = set(), 0
    for n, page in enumerate(data['pages'], 1):
        r._keys(page, 'page width_mm height_mm rotation rectangles')
        r._integer(page['page'], n, n); r._integer(page['rotation'], 0, 0)
        r._number(page['width_mm'], True); r._number(page['height_mm'], True)
        if not isinstance(page['rectangles'], list):
            raise ValueError('矩形の一覧が不正です。')
        previous = 0
        for rect in page['rectangles']:
            r._keys(rect, 'rectangle_id annotation_order x y width height purpose name expected required output_order join')
            r._integer(rect['annotation_order'], previous + 1, 2**31 - 1)
            previous = rect['annotation_order']
            if rect['rectangle_id'] != f'p{n:04d}-a{previous:06d}':
                raise ValueError('矩形の識別情報が不正です。')
            for key in ('x', 'y', 'width', 'height'):
                r._number(rect[key], key in ('width', 'height'))
            if (rect['x'] < 0 or rect['y'] < 0 or
                    rect['x'] + rect['width'] > page['width_mm'] + 1e-8 or
                    rect['y'] + rect['height'] > page['height_mm'] + 1e-8):
                raise ValueError(f'ページ{n}の矩形がページ範囲外です。')
            if rect['purpose'] not in ('field', 'condition') or rect['join'] not in JOINS:
                raise ValueError('矩形の用途または結合方法が不正です。')
            _name(rect['name'])
            key = (rect['purpose'], rect['name'])
            if key in names:
                raise ValueError(f'同じ用途の項目名が重複しています: {rect["name"]}')
            names.add(key)
            if type(rect['required']) is not bool:
                raise ValueError('必須は有無の属性を指定してください。')
            if rect['output_order'] is not None:
                r._integer(rect['output_order'], 1, 2**31 - 1)
            if rect['purpose'] == 'condition':
                _name(rect['expected'])
                if rect['expected'] != rect['expected'].strip():
                    raise ValueError('期待文字の前後に空白・改行を含めないでください。')
                if rect['required'] is not True or rect['output_order'] is not None:
                    raise ValueError('適用判定の属性が不正です。')
            else:
                fields += 1
                if rect['expected'] is not None:
                    raise ValueError('取得用矩形に期待文字は指定できません。')
    if not fields:
        raise ValueError('取得用の矩形が1つ以上必要です。')


@dataclass(frozen=True)
class RectangleTemplate:
    root: Path
    manifest_sha256: str
    _definition_bytes: bytes

    @property
    def data(self): return json.loads(self._definition_bytes)

    @property
    def template_id(self): return self.data['template_id']


def _sdk(dll_path):
    from ._template_sdk import TemplateSdk
    return TemplateSdk(dll_path)


def _load(root):
    digest = r.sha256(root/'manifest.json')
    manifest = r._manifest(root, SCHEMA, FILES)
    raw = (root/'template.json').read_bytes()
    data = r._read(root/'template.json')
    validate_template(data)
    if data['source_xdw_sha256'] != manifest['files']['source-template.xdw']:
        raise ValueError('テンプレートXDWのハッシュが一致しません。')
    r._manifest(root, SCHEMA, FILES)
    if r._digest(raw) != manifest['files']['template.json'] or r.sha256(root/'manifest.json') != digest:
        raise RuntimeError('読込中にテンプレートが変更されました。')
    return RectangleTemplate(root, digest, raw)


def load_rectangle_template(template_dir) -> RectangleTemplate:
    return _load(r._published(template_dir))


def register_rectangle_template(template_xdw, output_dir, *, name=None, dll_path=None) -> RectangleTemplate:
    source = r._plain_path(template_xdw)
    if source.suffix.lower() != '.xdw':
        raise ValueError('テンプレートにはXDWを指定してください。')
    name = _name(source.stem if name is None else name)
    output = r._destination(output_dir)
    with r.owned_directory(output.parent, '.rectangle-template-') as staging:
        digest = r._copy(source, staging/'source-template.xdw')
        snapshot = _sdk(dll_path).inspect(staging/'source-template.xdw')
        data = _compile(snapshot, name, digest)
        (staging/'template.json').write_bytes(r._bytes(data))
        r._write_manifest(staging, SCHEMA, FILES)
        _load(staging)
        if r.sha256(source) != digest:
            raise RuntimeError('登録中にテンプレートXDWが変更されました。')
        r.publish_new(staging, output)
    return load_rectangle_template(output)
