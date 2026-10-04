"""Independent, atomic Structured Result 1.0 bundles; no SDK on application/load."""
from dataclasses import dataclass
import json
from pathlib import Path
import uuid

from . import reviewed as r
from . import templates as t
from ._template_extract import evaluate

SCHEMA = 'docuworks-structured-result'
VERSION = '1.0'
FILES = {'structured.json', 'structured.jsonl', 'template.json', 'template-manifest.json',
         'reviewed.json', 'reviewed-manifest.json', 'identity.json', 'session.json'}


def _jsonl(data):
    # Exactly one document per row, even when applicability fails.
    return (json.dumps(data, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')


def _same(actual, expected):
    # Python equality would equate true and 1. Preserve JSON value types as well.
    return json.dumps(actual, sort_keys=True, ensure_ascii=False, allow_nan=False) == json.dumps(
        expected, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _snapshot_manifest(root, name, schema, version, names, copied):
    manifest = r._read(root/name)
    r._keys(manifest, 'schema schema_version status files'); r._header(manifest, schema, version)
    if manifest['status'] != 'COMPLETE' or not isinstance(manifest['files'], dict) or set(manifest['files']) != names:
        raise ValueError('参照元manifestの形式が不正です。')
    for filename, digest in manifest['files'].items():
        r._hash(digest)
        if filename in copied and r.sha256(r._plain_path(root/filename)) != digest:
            raise ValueError('参照元のJSONとmanifestが一致しません。')
    return manifest


def _inputs(root):
    template = r._read(root/'template.json'); t.validate_template(template)
    tm = _snapshot_manifest(root, 'template-manifest.json', t.SCHEMA, t.VERSION, t.FILES, {'template.json'})
    if template['source_xdw_sha256'] != tm['files']['source-template.xdw']:
        raise ValueError('テンプレートの参照元が不正です。')
    reviewed = r._read(root/'reviewed.json')
    if not isinstance(reviewed, dict) or reviewed.get('schema_version') not in ('1.0', '2.0'):
        raise ValueError('未対応のReviewed形式です。')
    version = reviewed['schema_version']
    rm = _snapshot_manifest(root, 'reviewed-manifest.json', r.RESULT_SCHEMA, version,
                            r.RESULT_FILES, {'reviewed.json','identity.json','session.json'})
    identity = r._identity(r._read(root/'identity.json')); session = r._read(root/'session.json')
    identity_hash = rm['files']['identity.json']
    r._validate_session(session, identity, identity_hash)
    if version == '2.0':
        from ._reviewed_v2 import validate_result
        validate_result(reviewed, identity, identity_hash)
    else:
        r._validate_result(reviewed, identity, session, identity_hash)
    if (reviewed['session_sha256'] != rm['files']['session.json'] or
            reviewed['source_xdw_sha256'] != rm['files']['source-review.xdw'] or
            r._digest(r._jsonl(reviewed)) != rm['files']['reviewed.jsonl']):
        raise ValueError('Reviewedの参照元・派生JSONLが不正です。')
    return template, reviewed


def _references(root, template, reviewed):
    return dict(template=dict(template_id=template['template_id'], name=template['name'],
                              manifest_sha256=r.sha256(root/'template-manifest.json'),
                              definition_sha256=r.sha256(root/'template.json')),
                reviewed=dict(result_id=reviewed['result_id'], schema_version=reviewed['schema_version'],
                              manifest_sha256=r.sha256(root/'reviewed-manifest.json'),
                              validation=reviewed.get('validation', dict(mode='strict', identity_checked=True,
                                                                        page_structure_checked=True))))


@dataclass(frozen=True)
class StructuredResult:
    root: Path
    manifest_sha256: str
    _result_bytes: bytes

    @property
    def data(self): return json.loads(self._result_bytes)

    @property
    def result_id(self): return self.data['result_id']


def _load(root):
    digest = r.sha256(root/'manifest.json')
    manifest = r._manifest(root, SCHEMA, FILES)
    template, reviewed = _inputs(root)
    data = r._read(root/'structured.json')
    r._keys(data, 'schema schema_version result_id created_at template reviewed applicable status diagnostics conditions fields')
    r._header(data, SCHEMA); r._uuid(data['result_id']); r._timestamp(data['created_at'])
    expected = dict(schema=SCHEMA, schema_version=VERSION, result_id=data['result_id'], created_at=data['created_at'],
                    **_references(root, template, reviewed), **evaluate(template, reviewed))
    if not _same(data, expected):
        raise ValueError('構造化結果が保存されたテンプレート・Reviewedと一致しません。')
    if (root/'structured.jsonl').read_bytes() != _jsonl(data):
        raise ValueError('派生JSONLが構造化結果JSONと一致しません。')
    raw = (root/'structured.json').read_bytes()
    r._manifest(root, SCHEMA, FILES)
    if r._digest(raw) != manifest['files']['structured.json'] or r.sha256(root/'manifest.json') != digest:
        raise RuntimeError('読込中に構造化結果が変更されました。')
    return StructuredResult(root, digest, raw)


def load_structured_result(result_dir) -> StructuredResult:
    """Validate saved source metadata and recompute extraction without DocuWorks."""
    return _load(r._published(result_dir))


def apply_rectangle_template(template_dir, reviewed_dir, output_dir) -> StructuredResult:
    template = t.load_rectangle_template(template_dir)
    reviewed = r.load_reviewed_result(reviewed_dir)
    output = r._destination(output_dir, template.root, reviewed.root)
    with r.owned_directory(output.parent, '.structured-result-') as staging:
        for source, names in ((template.root, ('template.json',)),
                              (reviewed.root, ('reviewed.json','identity.json','session.json'))):
            for name in names: r._copy(source/name, staging/name)
        r._copy(template.root/'manifest.json', staging/'template-manifest.json')
        r._copy(reviewed.root/'manifest.json', staging/'reviewed-manifest.json')
        if (r.sha256(staging/'template-manifest.json') != template.manifest_sha256 or
                r.sha256(staging/'reviewed-manifest.json') != reviewed.manifest_sha256):
            raise RuntimeError('適用中に参照元が変更されました。')
        td, rd = _inputs(staging)
        data = dict(schema=SCHEMA, schema_version=VERSION, result_id=str(uuid.uuid4()), created_at=r._now(),
                    **_references(staging, td, rd), **evaluate(td, rd))
        (staging/'structured.json').write_bytes(r._bytes(data))
        (staging/'structured.jsonl').write_bytes(_jsonl(data))
        r._write_manifest(staging, SCHEMA, FILES)
        _load(staging)
        if (t.load_rectangle_template(template.root) != template or r.load_reviewed_result(reviewed.root) != reviewed):
            raise RuntimeError('適用中に参照元が変更されました。')
        r.publish_new(staging, output)
    return load_structured_result(output)
