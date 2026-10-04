"""Explicit one-page XDW reviews. Native dependencies load only on execution."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import uuid

from ._storage import owned_directory, publish_new
from .corrections import TextCorrection, _decode, _destination, _hash, _keys, _recheck_run, _uuid
from .results import load_ocr_result, sha256

SCHEMA = 'docuworks-ocr-review'
IDENTITY_SCHEMA = 'docuworks-ocr-review-identity'
VERSION = '1.0'
MULTI_VERSION = '2.0'
ATTRIBUTE = 'DW-OCR.ReviewIdentity'
_TEXT = 'text'


@dataclass(frozen=True)
class ReviewEditCandidate:
    run_id: str
    manifest_sha256: str
    review_id: str
    review_manifest_sha256: str
    edited_xdw_sha256: str
    correction: TextCorrection | None


@dataclass(frozen=True)
class ReviewEditsCandidate:
    run_id: str
    manifest_sha256: str
    review_id: str
    review_manifest_sha256: str
    edited_xdw_sha256: str
    corrections: tuple[TextCorrection, ...]
    unchanged_region_ids: tuple[str, ...]


@dataclass(frozen=True)
class _Annotation:
    kind: str
    identity: bytes | None
    text: str | None
    x: float
    y: float


@dataclass(frozen=True)
class _Page:
    width: float
    height: float
    annotations: tuple[_Annotation, ...]


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def _region(result, region_id):
    if not isinstance(region_id, str):
        raise ValueError('review requires a string region ID')
    for page in result.pages:
        for region in page.regions:
            if region.id == region_id:
                return page, region
    raise ValueError('review region ID not found')


def _identity(manifest, digest):
    return dict(schema=IDENTITY_SCHEMA, schema_version=VERSION,
                review_id=manifest['review_id'], run_id=manifest['run_id'],
                manifest_sha256=manifest['manifest_sha256'], region_id=manifest['region_id'],
                review_manifest_sha256=digest)


def _dimensions(actual, expected):
    if abs(actual.width - expected.page_width_mm) > .01 or abs(actual.height - expected.page_height_mm) > .01:
        raise ValueError('review page dimensions do not match the source page')


def _target(snapshot, manifest, digest):
    tagged = [a for a in snapshot.annotations if a.identity is not None]
    if len(tagged) != 1:
        raise ValueError('review identity missing or duplicated')
    target = tagged[0]
    if target.kind != _TEXT:
        raise ValueError('review target is not a text annotation')
    data = _decode(target.identity)
    expected = _identity(manifest, digest)
    _keys(data, expected, 'review identity')
    if data != expected:
        raise ValueError('review identity does not match this source/review set')
    if len(snapshot.annotations) != manifest['annotation_count']:
        raise ValueError('review annotation structure changed')
    if not isinstance(target.text, str):
        raise ValueError('review text could not be read')
    return target


class _SdkBackend:
    """Small native boundary; all absent-attribute handling is confined here."""
    def __init__(self, dll_path):
        from docuworks_ctypes import XdwApi
        self.api = XdwApi.load(dll_path)

    @staticmethod
    def _attribute(annotation):
        import ctypes
        from docuworks_ctypes._raw.constants import XDW_E_INVALIDARG
        from docuworks_ctypes.errors import check_result
        raw = annotation.raw
        name = ATTRIBUTE.encode('ascii')
        size = raw.XDW_GetAnnotationUserAttribute(annotation.handle, name, None, 0, None)
        # Verified against installed XDWAPI: a missing name returns INVALIDARG.
        # Only this initial size query is eligible; never swallow data-read errors.
        if size == XDW_E_INVALIDARG:
            return None
        check_result(size, 'XDW_GetAnnotationUserAttribute(size)')
        if size == 0:
            return b''  # Present but invalid identity, not a missing attribute.
        buffer = (ctypes.c_char * size)()
        actual = raw.XDW_GetAnnotationUserAttribute(annotation.handle, name, buffer, size, None)
        check_result(actual, 'XDW_GetAnnotationUserAttribute(data)')
        if actual != size:
            raise RuntimeError('review identity changed while reading')
        return bytes(buffer)

    def extract(self, source, page, output):
        from docuworks_ctypes.encoding import wchar_buffer
        from docuworks_ctypes.errors import check_result
        with self.api.open_document(source) as document:
            check_result(self.api.raw.XDW_GetPageW(document.handle, page,
                         wchar_buffer(str(output)), None), 'XDW_GetPageW(review)')

    def inspect(self, path):
        from docuworks_ctypes import AnnotationType
        with self.api.open_document(path) as document:
            if document.page_count != 1:
                raise ValueError('review XDW must contain exactly one page')
            page = document.page(1)
            info = page._page_info()
            annotations = []
            for annotation in page.annotations(recursive=True):
                identity = self._attribute(annotation)
                kind = _TEXT if annotation.annotation_type == AnnotationType.TEXT else 'other'
                text = annotation.get_standard_attribute('%Text') if identity is not None and kind == _TEXT else None
                position = annotation.position
                annotations.append(_Annotation(kind, identity, text, position.x, position.y))
            return _Page(info.nWidth / 100, info.nHeight / 100, tuple(annotations))

    def add_text(self, path, region, identity):
        from docuworks_ctypes import PointMM, OpenMode, Color
        with self.api.open_document(path, mode=OpenMode.UPDATE) as document:
            annotation = document.page(1).add_text(
                PointMM(region.bbox_mm['x'], region.bbox_mm['y']), region.text,
                font_size=12, fore_color=Color.RED)
            annotation.set_user_attribute(ATTRIBUTE, identity)
            document.save()


def create_review_xdw(run_dir, region_id, output_dir, *, dll_path=None):
    """Create review.xdw + review.json atomically outside the saved OCR bundle."""
    original = load_ocr_result(run_dir)
    page, region = _region(original, region_id)
    output = _destination(output_dir, original.root)
    if re.fullmatch(r'\.review-[0-9a-f]{32}', output.name):
        raise ValueError('reserved private review directory name')
    backend = _SdkBackend(dll_path)
    with owned_directory(output.parent, '.review-') as staging:
        xdw = staging / 'review.xdw'
        backend.extract(original.root / original.source['path'], page.page, xdw)
        before = backend.inspect(xdw)
        _dimensions(before, page)
        if any(a.identity is not None for a in before.annotations):
            raise ValueError('source page already contains the reserved review attribute')
        manifest = dict(schema=SCHEMA, schema_version=VERSION, status='COMPLETE',
                        review_id=str(uuid.uuid4()), run_id=original.run_id,
                        manifest_sha256=original.manifest_sha256, region_id=region.id,
                        original_text=region.text, source_page=page.page, review_page=1,
                        page_width_mm=page.page_width_mm, page_height_mm=page.page_height_mm,
                        annotation_count=len(before.annotations) + 1)
        data = _json_bytes(manifest)
        digest = hashlib.sha256(data).hexdigest()
        backend.add_text(xdw, region, _json_bytes(_identity(manifest, digest)))
        after = backend.inspect(xdw)
        _dimensions(after, page)
        target = _target(after, manifest, digest)
        if target.text != region.text or abs(target.x - region.bbox_mm['x']) > .01 or abs(target.y - region.bbox_mm['y']) > .01:
            raise RuntimeError('review text/position did not survive save and reopen')
        (staging / 'review.json').write_bytes(data)
        if (staging / 'review.json').read_bytes() != data:
            raise RuntimeError('review manifest changed during creation')
        _recheck_run(original)
        publish_new(staging, output)
    return output


def _manifest(review_dir, original):
    root = Path(review_dir).resolve()
    if root.is_relative_to(original.root):
        raise ValueError('review set must be outside immutable OCR bundle')
    if re.fullmatch(r'\.review-[0-9a-f]{32}', root.name):
        raise ValueError('unpublished review set')
    path = root / 'review.json'
    data = path.read_bytes()
    manifest = _decode(data)
    _keys(manifest, ('schema', 'schema_version', 'status', 'review_id', 'run_id',
                    'manifest_sha256', 'region_id', 'original_text', 'source_page',
                    'review_page', 'page_width_mm', 'page_height_mm', 'annotation_count'), 'review manifest')
    if manifest['schema'] != SCHEMA or manifest['schema_version'] != VERSION or manifest['status'] != 'COMPLETE':
        raise ValueError('unsupported/incomplete review manifest')
    _uuid(manifest['review_id'], 'review ID')
    _uuid(manifest['run_id'], 'run ID')
    _hash(manifest['manifest_sha256'])
    if manifest['run_id'] != original.run_id or manifest['manifest_sha256'] != original.manifest_sha256:
        raise ValueError('review set targets a different source run')
    page, region = _region(original, manifest['region_id'])
    for key in ('source_page', 'review_page', 'annotation_count'):
        if type(manifest[key]) is not int or manifest[key] < 1:
            raise ValueError(f'invalid review {key}')
    for key in ('page_width_mm', 'page_height_mm'):
        if type(manifest[key]) not in (int, float) or manifest[key] != getattr(page, key):
            raise ValueError('review manifest page dimensions mismatch')
    if manifest['source_page'] != page.page or manifest['review_page'] != 1 or manifest['original_text'] != region.text:
        raise ValueError('review manifest source region mismatch')
    return path, data, manifest, page, region


def read_review_edit(run_dir, review_dir, edited_xdw, *, dll_path=None):
    """Read one explicitly matched edit; text validity belongs to corrections."""
    original = load_ocr_result(run_dir)
    manifest_path, data, manifest, page, region = _manifest(review_dir, original)
    edited = Path(edited_xdw).resolve()
    if edited.is_relative_to(original.root):
        raise ValueError('edited review must be outside immutable OCR bundle')
    digest = hashlib.sha256(data).hexdigest()
    edited_hash = sha256(edited)
    backend = _SdkBackend(dll_path)
    snapshot = backend.inspect(edited)
    _dimensions(snapshot, page)
    target = _target(snapshot, manifest, digest)
    correction = None if target.text == region.text else TextCorrection(region.id, region.text, target.text)
    _recheck_run(original)
    if manifest_path.read_bytes() != data or sha256(edited) != edited_hash:
        raise RuntimeError('review input changed while reading')
    return ReviewEditCandidate(original.run_id, original.manifest_sha256,
                               manifest['review_id'], digest, edited_hash, correction)


def _selected(original, region_ids):
    if isinstance(region_ids, (str, bytes)):
        raise ValueError('region IDs must be a nonempty collection')
    try:
        ids = tuple(region_ids)
    except TypeError as exc:
        raise ValueError('region IDs must be a nonempty collection') from exc
    if not ids or any(not isinstance(value, str) for value in ids):
        raise ValueError('region IDs must be nonempty strings')
    wanted = set(ids)
    if len(wanted) != len(ids):
        raise ValueError('duplicate review region ID')
    pairs = [_region(original, value) for value in ids]
    page = pairs[0][0]
    if any(other.page != page.page for other, _ in pairs):
        raise ValueError('review regions must belong to the same page')
    return page, tuple(region for region in page.regions if region.id in wanted)


def _multi_identity(manifest, digest, region_id):
    return dict(schema=IDENTITY_SCHEMA, schema_version=MULTI_VERSION,
                review_id=manifest['review_id'], run_id=manifest['run_id'],
                manifest_sha256=manifest['manifest_sha256'], region_id=region_id,
                review_manifest_sha256=digest)


def _multi_targets(snapshot, manifest, digest):
    expected_ids = {entry['region_id'] for entry in manifest['regions']}
    targets = {}
    if len(snapshot.annotations) != manifest['annotation_count']:
        raise ValueError('review annotation structure changed')
    for annotation in snapshot.annotations:
        if annotation.identity is None:
            continue
        data = _decode(annotation.identity)
        expected = _multi_identity(manifest, digest, None)
        _keys(data, expected, 'review identity')
        region_id = data['region_id']
        if not isinstance(region_id, str) or region_id not in expected_ids:
            raise ValueError('unknown review region identity')
        if region_id in targets:
            raise ValueError('duplicate review region identity')
        if data != _multi_identity(manifest, digest, region_id):
            raise ValueError('review identity does not match this source/review set')
        if annotation.kind != _TEXT or not isinstance(annotation.text, str):
            raise ValueError('review target is not readable text')
        targets[region_id] = annotation
    if set(targets) != expected_ids:
        raise ValueError('review region identity missing')
    return targets


def create_review_xdw_regions(run_dir, region_ids, output_dir, *, dll_path=None):
    """Create a format-2.0 review for explicit IDs on one page, in source order."""
    original = load_ocr_result(run_dir)
    page, regions = _selected(original, region_ids)
    output = _destination(output_dir, original.root)
    if re.fullmatch(r'\.review-[0-9a-f]{32}', output.name):
        raise ValueError('reserved private review directory name')
    backend = _SdkBackend(dll_path)
    with owned_directory(output.parent, '.review-') as staging:
        xdw = staging / 'review.xdw'
        backend.extract(original.root / original.source['path'], page.page, xdw)
        before = backend.inspect(xdw)
        _dimensions(before, page)
        if any(a.identity is not None for a in before.annotations):
            raise ValueError('source page already contains the reserved review attribute')
        manifest = dict(schema=SCHEMA, schema_version=MULTI_VERSION, status='COMPLETE',
                        review_id=str(uuid.uuid4()), run_id=original.run_id,
                        manifest_sha256=original.manifest_sha256,
                        regions=[dict(region_id=r.id, original_text=r.text) for r in regions],
                        source_page=page.page, review_page=1,
                        page_width_mm=page.page_width_mm, page_height_mm=page.page_height_mm,
                        annotation_count=len(before.annotations) + len(regions))
        data = _json_bytes(manifest)
        digest = hashlib.sha256(data).hexdigest()
        for region in regions:
            backend.add_text(xdw, region, _json_bytes(_multi_identity(manifest, digest, region.id)))
        after = backend.inspect(xdw)
        _dimensions(after, page)
        targets = _multi_targets(after, manifest, digest)
        for region in regions:
            target = targets[region.id]
            if target.text != region.text or abs(target.x - region.bbox_mm['x']) > .01 or abs(target.y - region.bbox_mm['y']) > .01:
                raise RuntimeError('review text/position did not survive save and reopen')
        (staging / 'review.json').write_bytes(data)
        if (staging / 'review.json').read_bytes() != data:
            raise RuntimeError('review manifest changed during creation')
        _recheck_run(original)
        publish_new(staging, output)
    return output


def _multi_manifest(review_dir, original):
    root = Path(review_dir).resolve()
    if root.is_relative_to(original.root):
        raise ValueError('review set must be outside immutable OCR bundle')
    if re.fullmatch(r'\.review-[0-9a-f]{32}', root.name):
        raise ValueError('unpublished review set')
    path = root / 'review.json'
    data = path.read_bytes()
    manifest = _decode(data)
    _keys(manifest, ('schema', 'schema_version', 'status', 'review_id', 'run_id',
                    'manifest_sha256', 'regions', 'source_page', 'review_page',
                    'page_width_mm', 'page_height_mm', 'annotation_count'), 'review manifest')
    if manifest['schema'] != SCHEMA or manifest['schema_version'] != MULTI_VERSION or manifest['status'] != 'COMPLETE':
        raise ValueError('unsupported/incomplete multi-region review manifest')
    _uuid(manifest['review_id'], 'review ID')
    _uuid(manifest['run_id'], 'run ID')
    _hash(manifest['manifest_sha256'])
    if manifest['run_id'] != original.run_id or manifest['manifest_sha256'] != original.manifest_sha256:
        raise ValueError('review set targets a different source run')
    entries = manifest['regions']
    if not isinstance(entries, list) or not entries:
        raise ValueError('review requires region entries')
    for entry in entries:
        _keys(entry, ('region_id', 'original_text'), 'review region')
    page, regions = _selected(original, [entry['region_id'] for entry in entries])
    if entries != [dict(region_id=r.id, original_text=r.text) for r in regions]:
        raise ValueError('review manifest source regions/order mismatch')
    for key in ('source_page', 'review_page', 'annotation_count'):
        if type(manifest[key]) is not int or manifest[key] < 1:
            raise ValueError(f'invalid review {key}')
    for key in ('page_width_mm', 'page_height_mm'):
        if type(manifest[key]) not in (int, float) or manifest[key] != getattr(page, key):
            raise ValueError('review manifest page dimensions mismatch')
    if manifest['source_page'] != page.page or manifest['review_page'] != 1 or manifest['annotation_count'] < len(regions):
        raise ValueError('review manifest page/count mismatch')
    return path, data, manifest, page, regions


def read_review_edits(run_dir, review_dir, edited_xdw, *, dll_path=None):
    """Read a complete format-2.0 review; text validity belongs to corrections."""
    original = load_ocr_result(run_dir)
    manifest_path, data, manifest, page, regions = _multi_manifest(review_dir, original)
    edited = Path(edited_xdw).resolve()
    if edited.is_relative_to(original.root):
        raise ValueError('edited review must be outside immutable OCR bundle')
    digest = hashlib.sha256(data).hexdigest()
    edited_hash = sha256(edited)
    snapshot = _SdkBackend(dll_path).inspect(edited)
    _dimensions(snapshot, page)
    targets = _multi_targets(snapshot, manifest, digest)
    corrections = tuple(TextCorrection(r.id, r.text, targets[r.id].text) for r in regions if targets[r.id].text != r.text)
    unchanged = tuple(r.id for r in regions if targets[r.id].text == r.text)
    _recheck_run(original)
    if manifest_path.read_bytes() != data or sha256(edited) != edited_hash:
        raise RuntimeError('review input changed while reading')
    return ReviewEditsCandidate(original.run_id, original.manifest_sha256,
                               manifest['review_id'], digest, edited_hash, corrections, unchanged)
