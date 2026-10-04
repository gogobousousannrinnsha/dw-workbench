"""Explicit, immutable-source OCR text corrections; standard library only."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import uuid

from ._storage import cleanup_owned, publish_new
from .results import CanonicalOcrRegion, OcrPageResult, load_ocr_result

SCHEMA = 'docuworks-ocr-corrections'
EFFECTIVE_SCHEMA = 'docuworks-ocr-effective-region'
VERSION = '1.0'


@dataclass(frozen=True)
class TextCorrection:
    region_id: str
    before_text: str
    after_text: str


@dataclass(frozen=True)
class CorrectionSet:
    correction_set_id: str
    run_id: str
    manifest_sha256: str
    edits: tuple[TextCorrection, ...]
    path: Path
    correction_set_sha256: str
    schema_version: str = VERSION


@dataclass(frozen=True)
class EffectiveOcrRegion(CanonicalOcrRegion):
    original_text: str
    is_corrected: bool


@dataclass(frozen=True)
class EffectiveOcrPage(OcrPageResult):
    regions: tuple[EffectiveOcrRegion, ...]


@dataclass(frozen=True)
class EffectiveOcrResult:
    run_id: str
    manifest_sha256: str
    correction_set_id: str
    correction_set_sha256: str
    source: dict
    ocr: dict
    pages: tuple[EffectiveOcrPage, ...]
    schema_version: str
    root: Path = field(repr=False)
    corrections: CorrectionSet = field(repr=False)


def _keys(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f'invalid {label} fields')


def _uuid(value, label):
    if not isinstance(value, str):
        raise ValueError(f'invalid {label}')
    try:
        valid = str(uuid.UUID(value)) == value
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(f'invalid {label}')


def _hash(value):
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('invalid SHA-256')


def _validate_edits(edits):
    seen = set()
    for edit in edits:
        if type(edit) is not TextCorrection:
            raise ValueError('edits must contain TextCorrection values')
        if not isinstance(edit.region_id, str) or not re.fullmatch(r'p\d{4,}-r\d{6,}', edit.region_id, re.ASCII):
            raise ValueError('invalid region ID')
        if edit.region_id in seen:
            raise ValueError(f'duplicate correction: {edit.region_id}')
        seen.add(edit.region_id)
        for value in (edit.before_text, edit.after_text):
            if not isinstance(value, str) or not value.strip():
                raise ValueError('correction text must be nonblank')
            # Reject lone surrogates before beginning a UTF-8 write.
            value.encode('utf-8')
        if edit.before_text == edit.after_text:
            raise ValueError(f'unchanged correction: {edit.region_id}')


def _payload(corrections):
    return dict(schema=SCHEMA, schema_version=corrections.schema_version,
                correction_set_id=corrections.correction_set_id,
                run_id=corrections.run_id, manifest_sha256=corrections.manifest_sha256,
                edits=[asdict(edit) for edit in corrections.edits])


def _decode(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'duplicate JSON key: {key}')
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f'invalid JSON constant: {value}')

    return json.loads(data.decode('utf-8'), object_pairs_hook=unique,
                      parse_constant=invalid_constant)


def load_corrections(path):
    """Read and validate one correction file, hashing the exact bytes parsed."""
    path = Path(path).resolve()
    data = path.read_bytes()
    payload = _decode(data)
    _keys(payload, ('schema', 'schema_version', 'correction_set_id', 'run_id',
                    'manifest_sha256', 'edits'), 'correction set')
    if payload['schema'] != SCHEMA or payload['schema_version'] != VERSION:
        raise ValueError('unsupported correction schema/version')
    _uuid(payload['correction_set_id'], 'correction set ID')
    _uuid(payload['run_id'], 'run ID')
    _hash(payload['manifest_sha256'])
    if not isinstance(payload['edits'], list):
        raise ValueError('edits must be a JSON array')
    edits = []
    for item in payload['edits']:
        _keys(item, ('region_id', 'before_text', 'after_text'), 'correction')
        edits.append(TextCorrection(**item))
    _validate_edits(edits)
    return CorrectionSet(payload['correction_set_id'], payload['run_id'],
                         payload['manifest_sha256'], tuple(edits), path,
                         hashlib.sha256(data).hexdigest())


def _match(result, corrections):
    if result.run_id != corrections.run_id:
        raise ValueError('correction set targets a different run')
    if result.manifest_sha256 != corrections.manifest_sha256:
        raise RuntimeError('correction source manifest mismatch')
    if corrections.path.is_relative_to(result.root):
        raise ValueError('correction file must be outside immutable bundle')
    regions = {r.id: r for page in result.pages for r in page.regions}
    for edit in corrections.edits:
        if edit.region_id not in regions:
            raise ValueError(f'unknown region ID: {edit.region_id}')
        if regions[edit.region_id].text != edit.before_text:
            raise ValueError(f'correction before_text mismatch: {edit.region_id}')


def _recheck_run(original):
    current = load_ocr_result(original.root)
    if current.run_id != original.run_id or current.manifest_sha256 != original.manifest_sha256:
        raise RuntimeError('source result changed during correction operation')
    return current


def _destination(output, root):
    raw = Path(output).absolute()
    if os.path.lexists(raw):
        raise FileExistsError(raw)
    output = raw.resolve()
    if output.is_relative_to(root):
        raise ValueError('derived output must be outside immutable bundle')
    if not output.parent.is_dir():
        raise FileNotFoundError(output.parent)
    return output


def _publish_file(temporary, output):
    if os.name == 'nt':
        # Windows rename atomically refuses an existing destination.
        publish_new(temporary, output)
    else:
        # POSIX rename could overwrite a concurrently created destination.
        os.link(temporary, output)


def _atomic_write(output, write, recheck):
    temporary = output.parent / ('.correction-' + uuid.uuid4().hex + '.tmp')
    created = False
    try:
        with temporary.open('x', encoding='utf-8', newline='\n') as stream:
            created = True
            write(stream)
            stream.flush()
            os.fsync(stream.fileno())
        recheck()
        _publish_file(temporary, output)
    finally:
        if created:
            cleanup_owned(temporary, primary=sys.exc_info()[1])


def save_corrections(run_dir, edits, output):
    """Validate against a saved run and publish a new correction JSON file."""
    original = load_ocr_result(run_dir)
    edits = tuple(edits)
    _validate_edits(edits)
    output = _destination(output, original.root)
    corrections = CorrectionSet(str(uuid.uuid4()), original.run_id,
                                original.manifest_sha256, edits, output, '')
    _match(original, corrections)
    payload = _payload(corrections)

    def write(stream):
        json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')

    _atomic_write(output, write, lambda: _recheck_run(original))
    return load_corrections(output)


def _saved_corrections(corrections):
    if not isinstance(corrections, CorrectionSet):
        raise ValueError('a saved CorrectionSet is required')
    current = load_corrections(corrections.path)
    if current != corrections:
        raise RuntimeError('correction set changed since loading')
    return current


def _effective(original, corrections):
    edits = {edit.region_id: edit for edit in corrections.edits}
    pages = []
    for page in original.pages:
        regions = []
        for region in page.regions:
            data = asdict(region)
            data['original_text'] = region.text
            data['is_corrected'] = region.id in edits
            if region.id in edits:
                data['text'] = edits[region.id].after_text
            regions.append(EffectiveOcrRegion(**data))
        data = asdict(page)
        data['regions'] = tuple(regions)
        pages.append(EffectiveOcrPage(**data))
    return EffectiveOcrResult(original.run_id, original.manifest_sha256,
                              corrections.correction_set_id, corrections.correction_set_sha256,
                              deepcopy(original.source), deepcopy(original.ocr), tuple(pages),
                              original.schema_version, original.root, corrections)


def apply_corrections(run_dir, corrections):
    """Apply one saved correction set, without changing any source files."""
    original = load_ocr_result(run_dir)
    current = _saved_corrections(corrections)
    _match(original, current)
    return _effective(original, current)


def _snapshot(result):
    def path_value(value):
        if isinstance(value, Path):
            return str(value)
        raise ValueError('invalid effective result value')

    return json.dumps(asdict(result), sort_keys=True, ensure_ascii=False,
                      allow_nan=False, default=path_value)


def _recheck_effective(result):
    current = apply_corrections(result.root, result.corrections)
    if _snapshot(current) != _snapshot(result):
        raise RuntimeError('effective result modified since applying corrections')
    return current


def export_effective_jsonl(result, output):
    """Export all effective regions, retaining original text and provenance."""
    if not isinstance(result, EffectiveOcrResult):
        raise ValueError('EffectiveOcrResult is required')
    current = _recheck_effective(result)
    output = _destination(output, current.root)

    def write(stream):
        for page in sorted(current.pages, key=lambda item: item.page):
            for region in page.regions:
                row = dict(schema=EFFECTIVE_SCHEMA, schema_version=VERSION,
                           run_id=current.run_id, manifest_sha256=current.manifest_sha256,
                           correction_set_id=current.correction_set_id,
                           correction_set_sha256=current.correction_set_sha256,
                           page=page.page, **asdict(region))
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')

    _atomic_write(output, write, lambda: _recheck_effective(result))
    return output
