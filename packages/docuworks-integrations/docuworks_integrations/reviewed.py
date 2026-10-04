"""Immutable blank-review sessions and independent reviewed snapshots.

Loading saved data needs only the standard library. Native imports are lazy.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import uuid

from ._storage import owned_directory, publish_new
from .results import load_ocr_result, read_json, sha256

VERSION = '1.0'
SESSION_SCHEMA = 'docuworks-review-session'
RESULT_SCHEMA = 'docuworks-reviewed-result'
IDENTITY_SCHEMA = 'docuworks-review-session-identity'
COORDINATES = 'top-left-x-right-y-down'
SESSION_FILES = {'identity.json', 'session.json', 'initial.xdw'}
RESULT_FILES = {'identity.json', 'session.json', 'reviewed.json', 'reviewed.jsonl', 'source-review.xdw'}
ORIGIN_STATUSES = {'matched', 'missing', 'duplicate', 'invalid', 'foreign'}


def _bytes(data):
    return (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _keys(data, fields):
    if not isinstance(data, dict) or set(data) != set(fields.split()):
        raise ValueError('invalid reviewed object fields')


def _uuid(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError('invalid reviewed UUID')


def _hash(value):
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('invalid reviewed SHA-256')


def _number(value, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or (positive and value <= 0):
        raise ValueError('invalid reviewed geometry')


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('invalid reviewed integer')


def _timestamp(value):
    if not isinstance(value, str) or datetime.fromisoformat(value).utcoffset() is None:
        raise ValueError('timestamp must include timezone')


def _header(data, schema, version=VERSION):
    if data['schema'] != schema or data['schema_version'] != version:
        raise ValueError('unsupported reviewed schema/version')


def _plain_path(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ValueError('linked reviewed paths are unsupported')
    return path.resolve()


def _published(root):
    root = _plain_path(root)
    if root.name.startswith(('.review-session-', '.review-result-', '.review-export-', '.review-origins-', '.rectangle-template-', '.structured-result-', '.structured-csv-')):
        raise ValueError('unpublished review staging directory')
    return root


def _destination(path, *protected):
    path = _published(path)
    if os.path.lexists(path):
        raise FileExistsError(path)
    for root in protected:
        root = Path(root).resolve()
        if path == root or path.is_relative_to(root):
            raise ValueError('output must be outside immutable input')
    if not path.parent.is_dir():
        raise FileNotFoundError(path.parent)
    for parent in path.parents:
        marker = parent / 'manifest.json'
        if marker.is_file():
            manifest = _read(marker)
            if isinstance(manifest, dict) and manifest.get('schema') in ('docuworks-ocr-result', SESSION_SCHEMA, RESULT_SCHEMA, 'docuworks-rectangle-template', 'docuworks-structured-result'):
                raise ValueError('output must be outside saved result bundles')
    return path


def _read(path):
    _plain_path(path)
    return read_json(path)


def _manifest(root, schema, expected, version=VERSION):
    data = _read(root / 'manifest.json')
    _keys(data, 'schema schema_version status files')
    _header(data, schema, version)
    if data['status'] != 'COMPLETE' or not isinstance(data['files'], dict) or set(data['files']) != expected:
        raise ValueError('incomplete reviewed bundle')
    for name, digest in data['files'].items():
        _hash(digest)
        if sha256(_plain_path(root / name)) != digest:
            raise RuntimeError(f'reviewed input changed: {name}')
    return data


def _write_manifest(root, schema, names, version=VERSION):
    (root / 'manifest.json').write_bytes(_bytes(dict(schema=schema, schema_version=version,
        status='COMPLETE', files={name: sha256(root / name) for name in sorted(names)})))


def _copy(source, destination):
    source = _plain_path(source)
    before = sha256(source)
    with source.open('rb') as src, destination.open('xb') as dst:
        import shutil
        shutil.copyfileobj(src, dst)
        dst.flush()
        os.fsync(dst.fileno())
    if sha256(source) != before or sha256(destination) != before:
        raise RuntimeError('reviewed input changed during copy')
    return before


def _identity(data):
    _keys(data, 'schema schema_version review_id run_id canonical_manifest_sha256 source_sha256 pages')
    _header(data, IDENTITY_SCHEMA)
    _uuid(data['review_id']); _uuid(data['run_id'])
    _hash(data['canonical_manifest_sha256']); _hash(data['source_sha256'])
    if not isinstance(data['pages'], list) or not data['pages']:
        raise ValueError('review session requires all pages')
    seen_pages, seen_annotations, seen_regions = set(), set(), set()
    for n, page in enumerate(data['pages'], 1):
        _keys(page, 'page page_id width_mm height_mm items')
        _integer(page['page'], n, n); _uuid(page['page_id'])
        if page['page_id'] in seen_pages:
            raise ValueError('duplicate page ID')
        seen_pages.add(page['page_id'])
        _number(page['width_mm'], True); _number(page['height_mm'], True)
        if not isinstance(page['items'], list):
            raise ValueError('invalid identity items')
        for item in page['items']:
            _keys(item, 'annotation_id region_id text x y')
            _uuid(item['annotation_id'])
            if not isinstance(item['region_id'], str) or re.fullmatch(rf'p{n:04d}-r[0-9]{{6,}}', item['region_id']) is None:
                raise ValueError('invalid source region ID')
            if item['annotation_id'] in seen_annotations or item['region_id'] in seen_regions:
                raise ValueError('duplicate generated identity')
            seen_annotations.add(item['annotation_id']); seen_regions.add(item['region_id'])
            if not isinstance(item['text'], str) or not item['text'].strip():
                raise ValueError('invalid initial OCR text')
            _number(item['x']); _number(item['y'])
    return data


def _geometry(item):
    if not isinstance(item['text'], str):
        raise ValueError('unreadable review text')
    for name in ('x', 'y', 'width', 'height'):
        _number(item[name], name in ('width', 'height'))
    _integer(item['rotation'], 0, 359); _integer(item['direction'], 0, 1)


def _same_dimensions(a, b):
    return all(abs(a[k] - b[k]) <= .010000001 for k in ('width_mm', 'height_mm'))


def _validate_session(data, identity, identity_hash):
    _keys(data, 'schema schema_version review_id identity_sha256 created_at generator initial_sha256 pages')
    _header(data, SESSION_SCHEMA); _timestamp(data['created_at']); _hash(data['initial_sha256'])
    if data['review_id'] != identity['review_id'] or data['identity_sha256'] != identity_hash:
        raise ValueError('session identity mismatch')
    if not isinstance(data['generator'], dict) or not isinstance(data['pages'], list) or len(data['pages']) != len(identity['pages']):
        raise ValueError('invalid session pages/generator')
    for page, expected in zip(data['pages'], identity['pages']):
        _keys(page, 'page page_id width_mm height_mm rotation items')
        _integer(page['page'], expected['page'], expected['page'])
        _integer(page['rotation'], 0, 0)
        _number(page['width_mm'], True); _number(page['height_mm'], True)
        if page['page_id'] != expected['page_id'] or not _same_dimensions(page, expected):
            raise ValueError('session page mismatch')
        if not isinstance(page['items'], list) or len(page['items']) != len(expected['items']):
            raise ValueError('session initial items mismatch')
        for item, old in zip(page['items'], expected['items']):
            _keys(item, 'annotation_id region_id text x y width height rotation direction font_name font_size')
            _geometry(item)
            if any(item[k] != old[k] for k in ('annotation_id', 'region_id', 'text')):
                raise ValueError('session initial text/identity mismatch')
            if any(abs(item[k] - old[k]) > .010000001 for k in ('x', 'y')):
                raise ValueError('session initial position mismatch')
            if item['rotation'] or item['direction'] or item['font_size'] != 12 or not isinstance(item['font_name'], str):
                raise ValueError('session initial style mismatch')


@dataclass(frozen=True)
class ReviewSession:
    root: Path
    manifest_sha256: str
    _identity_bytes: bytes
    _session_bytes: bytes

    @property
    def review_id(self): return self.data['review_id']
    @property
    def data(self): return json.loads(self._session_bytes)
    @property
    def identity(self): return json.loads(self._identity_bytes)
    @property
    def pages(self): return tuple(self.data['pages'])
    @property
    def review_xdw(self): return self.root / 'review.xdw'


@dataclass(frozen=True)
class ReviewedResult:
    root: Path
    manifest_sha256: str
    _result_bytes: bytes

    @property
    def result_id(self): return self.data['result_id']
    @property
    def review_id(self): return self.data['review_id']
    @property
    def data(self): return json.loads(self._result_bytes)
    @property
    def pages(self): return tuple(self.data['pages'])


def _load_session(root):
    manifest_hash = sha256(root / 'manifest.json')
    manifest = _manifest(root, SESSION_SCHEMA, SESSION_FILES)
    identity = _identity(_read(root / 'identity.json'))
    data = _read(root / 'session.json')
    _validate_session(data, identity, manifest['files']['identity.json'])
    if data['initial_sha256'] != manifest['files']['initial.xdw']:
        raise ValueError('initial XDW hash mismatch')
    identity_bytes = (root / 'identity.json').read_bytes()
    session_bytes = (root / 'session.json').read_bytes()
    if (_digest(identity_bytes) != manifest['files']['identity.json'] or
            _digest(session_bytes) != manifest['files']['session.json'] or
            sha256(root / 'manifest.json') != manifest_hash):
        raise RuntimeError('review session changed while loading')
    return ReviewSession(root, manifest_hash, identity_bytes, session_bytes)


def load_review_session(session_dir) -> ReviewSession:
    """Load immutable session metadata, without opening editable review.xdw or loading a DLL."""
    return _load_session(_published(session_dir))


def _sdk(dll_path):
    from ._reviewed_sdk import ReviewSdk
    return ReviewSdk(dll_path)


def _decode(value):
    if value is None:
        return None
    try:
        def pairs(items):
            result = {}
            for k, v in items:
                if k in result: raise ValueError('duplicate identity key')
                result[k] = v
            return result
        data = json.loads(value, object_pairs_hook=pairs)
        return data if isinstance(data, dict) else None
    except (ValueError, UnicodeError, RecursionError):
        return None


def _match_pages(snapshot, identity, identity_hash):
    common = dict(review_id=identity['review_id'], identity_sha256=identity_hash)
    if _decode(snapshot['identity']) != common:
        raise ValueError('review document identity missing or mismatched')
    if len(snapshot['pages']) != len(identity['pages']):
        raise ValueError('review page count changed')
    for page, expected in zip(snapshot['pages'], identity['pages']):
        if (page['page'] != expected['page'] or page['rotation'] != 0 or not _same_dimensions(page, expected)
                or _decode(page['identity']) != dict(common, page_id=expected['page_id'])):
            raise ValueError(f"page {expected['page']}: identity/order/dimensions/rotation changed")


def create_review_session(run_dir, output_dir, *, dll_path=None,
                          review_creation_mode='document') -> ReviewSession:
    """Create immutable initial.xdw + metadata and an editable review.xdw, outside Canonical."""
    if review_creation_mode not in ('document', 'page_join'):
        raise ValueError('review_creation_mode must be document or page_join')
    original = load_ocr_result(run_dir)
    output = _destination(output_dir, original.root)
    count = original.source.get('page_count')
    if type(count) is not int or [p.page for p in original.pages] != list(range(1, count + 1)):
        raise ValueError('review requires a complete document with known page count')
    backend = _sdk(dll_path)
    source_pages = backend.source_pages(original.root / original.source['path'])
    if len(source_pages) != count or any(abs(w-p.page_width_mm) > .01 or abs(h-p.page_height_mm) > .01
                                        for (w,h),p in zip(source_pages, original.pages)):
        raise ValueError('Canonical page dimensions/count differ from source XDW')
    identity = dict(schema=IDENTITY_SCHEMA, schema_version=VERSION, review_id=str(uuid.uuid4()),
                    run_id=original.run_id, canonical_manifest_sha256=original.manifest_sha256,
                    source_sha256=original.source['sha256'], pages=[])
    for p in original.pages:
        identity['pages'].append(dict(page=p.page, page_id=str(uuid.uuid4()), width_mm=p.page_width_mm,
            height_mm=p.page_height_mm, items=[dict(annotation_id=str(uuid.uuid4()), region_id=r.id,
            text=r.text, x=r.bbox_mm['x'], y=r.bbox_mm['y']) for r in p.regions]))
    _identity(identity)
    identity_bytes = _bytes(identity); identity_hash = _digest(identity_bytes)
    with owned_directory(output.parent, '.review-session-') as staging:
        (staging / 'identity.json').write_bytes(identity_bytes)
        from ._performance import measure
        create = backend.create if review_creation_mode == 'document' else backend.create_page_join
        with measure('review.create'):
            generator = create(identity, identity_hash, staging / 'initial.xdw')
        with measure('review.inspect'):
            snapshot = backend.inspect(staging / 'initial.xdw')
            _match_pages(snapshot, identity, identity_hash)
        from . import __version__
        generator.update(integrations=__version__, review_creation_mode=review_creation_mode)
        data = dict(schema=SESSION_SCHEMA, schema_version=VERSION, review_id=identity['review_id'],
                    identity_sha256=identity_hash, created_at=_now(), generator=generator,
                    initial_sha256=sha256(staging / 'initial.xdw'), pages=[])
        for page, expected in zip(snapshot['pages'], identity['pages']):
            items = []
            if len(page['items']) != len(expected['items']):
                raise RuntimeError('generated review annotation count mismatch')
            for item, old in zip(page['items'], expected['items']):
                tagged = dict(review_id=identity['review_id'], identity_sha256=identity_hash,
                              annotation_id=old['annotation_id'], region_id=old['region_id'])
                if _decode(item['identity']) != tagged:
                    raise RuntimeError('generated review annotation identity mismatch')
                if item['fore_color'] != 255 or item['word_wrap']:
                    raise RuntimeError('generated review color/wrap mismatch')
                items.append(dict({k:v for k,v in item.items() if k not in ('identity', 'fore_color', 'word_wrap')},
                                  annotation_id=old['annotation_id'], region_id=old['region_id']))
            data['pages'].append(dict(page=page['page'], page_id=expected['page_id'],
                width_mm=page['width_mm'], height_mm=page['height_mm'], rotation=page['rotation'], items=items))
        (staging / 'session.json').write_bytes(_bytes(data))
        _copy(staging / 'initial.xdw', staging / 'review.xdw')
        _write_manifest(staging, SESSION_SCHEMA, SESSION_FILES)
        _load_session(staging)
        if load_ocr_result(original.root).manifest_sha256 != original.manifest_sha256:
            raise RuntimeError('Canonical changed during review generation')
        publish_new(staging, output)
    return load_review_session(output)


def _origin(raw, identity, identity_hash):
    evidence = None if raw is None else base64.b64encode(raw).decode('ascii')
    result = dict(status='missing' if raw is None else 'invalid', annotation_id=None, region_id=None, raw_base64=evidence)
    data = _decode(raw)
    if data is None or set(data) != {'review_id', 'identity_sha256', 'annotation_id', 'region_id'}:
        return result
    if not all(isinstance(v, str) for v in data.values()):
        return result
    try:
        _uuid(data['review_id']); _uuid(data['annotation_id']); _hash(data['identity_sha256'])
        if re.fullmatch(r'p[0-9]{4,}-r[0-9]{6,}', data['region_id']) is None:
            return result
    except ValueError:
        return result
    if data['review_id'] != identity['review_id'] or data['identity_sha256'] != identity_hash:
        result['status'] = 'foreign'
        return result
    known = {i['annotation_id']: i['region_id'] for p in identity['pages'] for i in p['items']}
    if known.get(data['annotation_id']) == data['region_id']:
        result.update(status='matched', annotation_id=data['annotation_id'], region_id=data['region_id'])
    return result


def _jsonl(data):
    if data.get('schema_version') == '2.0':
        from ._reviewed_v2 import jsonl
        return jsonl(data)
    rows = []
    for p in data['pages']:
        for item in p['items']:
            rows.append(json.dumps(dict(schema='docuworks-reviewed-text', schema_version=VERSION,
                result_id=data['result_id'], review_id=data['review_id'], page=p['page'], page_id=p['page_id'],
                coordinate_system=COORDINATES, unit='mm', **item), ensure_ascii=False, allow_nan=False) + '\n')
    return ''.join(rows).encode('utf-8')


def _validate_result(data, identity, session, identity_hash):
    _keys(data, 'schema schema_version result_id review_id created_at source_xdw_sha256 session_sha256 coordinate_system unit pages')
    _header(data, RESULT_SCHEMA); _uuid(data['result_id']); _timestamp(data['created_at'])
    _hash(data['source_xdw_sha256']); _hash(data['session_sha256'])
    if data['review_id'] != identity['review_id'] or data['coordinate_system'] != COORDINATES or data['unit'] != 'mm':
        raise ValueError('reviewed result identity/coordinates mismatch')
    if not isinstance(data['pages'], list) or len(data['pages']) != len(session['pages']):
        raise ValueError('reviewed page count mismatch')
    ids, origins = set(), []
    for page, expected in zip(data['pages'], session['pages']):
        _keys(page, 'page page_id width_mm height_mm rotation items')
        _integer(page['page'], expected['page'], expected['page']); _integer(page['rotation'], 0, 0)
        _number(page['width_mm'], True); _number(page['height_mm'], True)
        if any(page[k] != expected[k] for k in ('page', 'page_id', 'width_mm', 'height_mm', 'rotation')):
            raise ValueError('reviewed page metadata mismatch')
        if not isinstance(page['items'], list): raise ValueError('invalid reviewed items')
        for n, item in enumerate(page['items'], 1):
            _keys(item, 'item_id order text x y width height rotation direction origin diagnostics')
            _uuid(item['item_id']); _integer(item['order'], n, n); _geometry(item)
            if item['item_id'] in ids: raise ValueError('duplicate reviewed item ID')
            ids.add(item['item_id'])
            origin = item['origin']
            _keys(origin, 'status annotation_id region_id raw_base64')
            try:
                raw = None if origin['raw_base64'] is None else base64.b64decode(origin['raw_base64'], validate=True)
            except (ValueError, TypeError) as exc:
                raise ValueError('invalid origin evidence') from exc
            expected_origin = _origin(raw, identity, identity_hash)
            compare = dict(origin)
            if compare['status'] == 'duplicate': compare['status'] = 'matched'
            if compare != expected_origin: raise ValueError('origin evidence/status mismatch')
            origins.append(origin)
            diagnostics = ['EMPTY_TEXT'] if not item['text'].strip() else []
            if origin['status'] != 'matched': diagnostics.append('ORIGIN_' + origin['status'].upper())
            if item['diagnostics'] != diagnostics: raise ValueError('reviewed diagnostics mismatch')
    counts = Counter(o['annotation_id'] for o in origins if o['status'] in ('matched', 'duplicate'))
    for origin in origins:
        if origin['status'] in ('matched', 'duplicate') and (origin['status'] == 'duplicate') != (counts[origin['annotation_id']] > 1):
            raise ValueError('duplicate origin classification mismatch')


def _load_result(root):
    header = _read(root / 'manifest.json')
    if isinstance(header, dict) and header.get('schema_version') == '2.0':
        from ._reviewed_v2 import load_result
        return load_result(root)
    manifest_hash = sha256(root / 'manifest.json')
    manifest = _manifest(root, RESULT_SCHEMA, RESULT_FILES)
    identity = _identity(_read(root / 'identity.json'))
    session = _read(root / 'session.json')
    _validate_session(session, identity, manifest['files']['identity.json'])
    data = _read(root / 'reviewed.json')
    _validate_result(data, identity, session, manifest['files']['identity.json'])
    if data['session_sha256'] != manifest['files']['session.json'] or data['source_xdw_sha256'] != manifest['files']['source-review.xdw']:
        raise ValueError('reviewed source/session hashes mismatch')
    if (root / 'reviewed.jsonl').read_bytes() != _jsonl(data):
        raise ValueError('reviewed JSONL differs from canonical reviewed JSON')
    result_bytes = (root / 'reviewed.json').read_bytes()
    if _digest(result_bytes) != manifest['files']['reviewed.json'] or sha256(root / 'manifest.json') != manifest_hash:
        raise RuntimeError('reviewed result changed while loading')
    return ReviewedResult(root, manifest_hash, result_bytes)


def load_reviewed_result(result_dir) -> ReviewedResult:
    """Validate and load an independent result bundle with no SDK/Canonical dependency."""
    return _load_result(_published(result_dir))


def import_reviewed_result(session_dir, edited_xdw, output_dir, *, dll_path=None,
                           validation_mode='strict') -> ReviewedResult:
    """Import one snapshot: legacy strict/1.0 (default), or identity/2.0."""
    if validation_mode == 'identity':
        from ._reviewed_v2 import import_result
        return import_result(session_dir, edited_xdw, output_dir, dll_path=dll_path)
    if validation_mode != 'strict':
        raise ValueError('validation_mode must be strict or identity')
    session = load_review_session(session_dir)
    edited = _plain_path(edited_xdw)
    if edited == session.root / 'initial.xdw':
        raise ValueError('initial.xdw is an immutable baseline; explicitly submit an editable copy')
    output = _destination(output_dir, session.root)
    identity = session.identity; identity_hash = _digest(session._identity_bytes)
    with owned_directory(output.parent, '.review-result-') as staging:
        input_hash = _copy(edited, staging / 'source-review.xdw')
        snapshot = _sdk(dll_path).inspect(staging / 'source-review.xdw')
        _match_pages(snapshot, identity, identity_hash)
        data = dict(schema=RESULT_SCHEMA, schema_version=VERSION, result_id=str(uuid.uuid4()),
            review_id=session.review_id, created_at=_now(), source_xdw_sha256=input_hash,
            session_sha256=_digest(session._session_bytes), coordinate_system=COORDINATES, unit='mm', pages=[])
        all_items = []
        for page, initial in zip(snapshot['pages'], session.pages):
            record = {k:v for k,v in initial.items() if k != 'items'}
            record['items'] = []
            # Page dimensions in the result are the actual imported values, not an estimated OCR box.
            if any(page[k] != initial[k] for k in ('width_mm', 'height_mm')):
                raise ValueError('review page dimensions changed')
            for n, raw in enumerate(page['items'], 1):
                _geometry(raw)
                item = {k:raw[k] for k in ('text', 'x', 'y', 'width', 'height', 'rotation', 'direction')}
                item.update(item_id=str(uuid.uuid4()), order=n,
                            origin=_origin(raw['identity'], identity, identity_hash), diagnostics=[])
                record['items'].append(item); all_items.append(item)
            data['pages'].append(record)
        counts = Counter(i['origin']['annotation_id'] for i in all_items if i['origin']['status'] == 'matched')
        for item in all_items:
            origin = item['origin']
            if origin['status'] == 'matched' and counts[origin['annotation_id']] > 1:
                origin['status'] = 'duplicate'
            if not item['text'].strip(): item['diagnostics'].append('EMPTY_TEXT')
            if origin['status'] != 'matched': item['diagnostics'].append('ORIGIN_' + origin['status'].upper())
        (staging / 'identity.json').write_bytes(session._identity_bytes)
        (staging / 'session.json').write_bytes(session._session_bytes)
        (staging / 'reviewed.json').write_bytes(_bytes(data))
        (staging / 'reviewed.jsonl').write_bytes(_jsonl(data))
        _write_manifest(staging, RESULT_SCHEMA, RESULT_FILES)
        _load_result(staging)
        if load_review_session(session.root) != session or sha256(edited) != input_hash:
            raise RuntimeError('review inputs changed during import')
        publish_new(staging, output)
    return load_reviewed_result(output)


def get_reviewed_origins(item):
    """Return valid region IDs from a validated 1.0 or 2.0 item; keep result context."""
    if 'origins' in item:
        return tuple(reference['region_id'] for reference in item['origins'])
    origin = item['origin']
    return (origin['region_id'],) if origin['status'] in ('matched', 'duplicate') else ()


def set_review_origins(session_dir, edited_xdw, output_xdw, assignments, *,
                       expected_source_sha256, dll_path=None):
    """Assign explicit region IDs to current page/text-order locators in a new XDW.

    assignments: [{'page': 1, 'order': 1, 'region_ids': ['p0001-r000001']}].
    The expected input hash prevents applying locators to a subsequently edited file.
    No source or existing bundle is overwritten.
    """
    from ._reviewed_v2 import set_origins
    return set_origins(session_dir, edited_xdw, output_xdw, assignments,
                       expected_source_sha256=expected_source_sha256, dll_path=dll_path)


def export_reviewed_jsonl(result: ReviewedResult, output_path) -> Path:
    """Export a saved, unchanged result to a new path outside its immutable bundle."""
    if not isinstance(result, ReviewedResult): raise TypeError('expected ReviewedResult')
    current = load_reviewed_result(result.root)
    if current != result: raise RuntimeError('saved reviewed result changed')
    output = _destination(output_path, result.root)
    with owned_directory(output.parent, '.review-export-') as staging:
        temp = staging / 'result.jsonl'
        temp.write_bytes(_jsonl(result.data))
        if load_reviewed_result(result.root) != result: raise RuntimeError('reviewed result changed during export')
        publish_new(temp, output)
    return output
