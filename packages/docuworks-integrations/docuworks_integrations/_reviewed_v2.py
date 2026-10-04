"""Identity-only snapshots and explicit provenance assignment (format 2.0).

Session/identity remain 1.0. The legacy reader and strict importer are unchanged.
This module does not import the SDK; persistence/validation are DLL independent.
"""
import base64
import copy
import json
import uuid

from . import reviewed as r

VERSION = '2.0'
ORIGIN_SCHEMA = 'docuworks-review-origins'
VALIDATION = dict(mode='identity', identity_checked=True, page_structure_checked=False)
REFERENCE_KEYS = 'run_id canonical_manifest_sha256 region_id'
ITEM_KEYS = 'item_id order text x y width height rotation direction origins origin_evidence diagnostics'
PAGE_KEYS = 'page page_id width_mm height_mm rotation items'
RESULT_KEYS = ('schema schema_version result_id review_id created_at source_xdw_sha256 '
               'session_sha256 coordinate_system unit pages validation excluded_sticky_count')


def reference(identity, region_id):
    return dict(run_id=identity['run_id'],
                canonical_manifest_sha256=identity['canonical_manifest_sha256'], region_id=region_id)


def origins(raw, identity, identity_hash):
    """Validate provenance independently of text, preserving all received evidence."""
    evidence = dict(status='none', raw_base64=None if raw is None else base64.b64encode(raw).decode('ascii'),
                    issues=[])
    if raw is None:
        return [], evidence
    data = r._decode(raw)
    if data is not None and 'schema' not in data:
        old = r._origin(raw, identity, identity_hash)
        if old['status'] == 'matched':
            evidence['status'] = 'matched'
            return [reference(identity, old['region_id'])], evidence
        reason = 'foreign' if old['status'] == 'foreign' else 'invalid'
        evidence.update(status=reason, issues=[dict(index=None, reason=reason)])
        return [], evidence
    try:
        r._keys(data, 'schema schema_version review_id identity_sha256 origins')
        r._header(data, ORIGIN_SCHEMA, VERSION)
        r._uuid(data['review_id']); r._hash(data['identity_sha256'])
        if not isinstance(data['origins'], list):
            raise ValueError('invalid origin list')
    except (ValueError, TypeError, AttributeError):
        evidence.update(status='invalid', issues=[dict(index=None, reason='invalid')])
        return [], evidence
    if data['review_id'] != identity['review_id'] or data['identity_sha256'] != identity_hash:
        evidence.update(status='foreign', issues=[dict(index=None, reason='foreign')])
        return [], evidence
    known = {i['region_id'] for page in identity['pages'] for i in page['items']}
    valid = {}
    for index, candidate in enumerate(data['origins']):
        reason = None
        try:
            r._keys(candidate, REFERENCE_KEYS)
            r._uuid(candidate['run_id']); r._hash(candidate['canonical_manifest_sha256'])
            if not isinstance(candidate['region_id'], str):
                raise ValueError('invalid region ID')
            if (candidate['run_id'] != identity['run_id'] or
                    candidate['canonical_manifest_sha256'] != identity['canonical_manifest_sha256']):
                reason = 'foreign'
            elif candidate['region_id'] not in known:
                reason = 'invalid'
        except (ValueError, TypeError, AttributeError):
            reason = 'invalid'
        if reason:
            evidence['issues'].append(dict(index=index, reason=reason))
        else:
            valid[candidate['region_id']] = reference(identity, candidate['region_id'])
    refs = [valid[key] for key in sorted(valid)]
    if evidence['issues']:
        evidence['status'] = ('partial' if refs else
                              'foreign' if all(i['reason'] == 'foreign' for i in evidence['issues']) else 'invalid')
    elif refs:
        evidence['status'] = 'matched'
    return refs, evidence


def diagnostics(text, evidence):
    result = ['EMPTY_TEXT'] if not text.strip() else []
    if evidence['status'] in ('invalid', 'foreign', 'partial'):
        result.append('ORIGIN_' + evidence['status'].upper())
    return result


def check_document(snapshot, identity, identity_hash):
    if r._decode(snapshot['identity']) != dict(review_id=identity['review_id'], identity_sha256=identity_hash):
        raise ValueError('review document identity missing or mismatched')


def check_pages(pages):
    # Check the snapshot's own representation, never compare against Session pages.
    if not isinstance(pages, list) or not pages:
        raise ValueError('unreadable review pages')
    for index, page in enumerate(pages, 1):
        r._integer(page['page'], index, index)
        r._number(page['width_mm'], True); r._number(page['height_mm'], True)
        r._integer(page['rotation'], 0, 359)
        if not isinstance(page['items'], list):
            raise ValueError('unreadable review items')


def jsonl(data):
    rows = []
    for page in data['pages']:
        for item in page['items']:
            row = dict(schema='docuworks-reviewed-text', schema_version=VERSION,
                       result_id=data['result_id'], review_id=data['review_id'],
                       page=page['page'], page_id=page['page_id'], coordinate_system=r.COORDINATES,
                       unit='mm', validation=data['validation'], **item)
            rows.append(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
    return ''.join(rows).encode('utf-8')


def validate_result(data, identity, identity_hash):
    r._keys(data, RESULT_KEYS); r._header(data, r.RESULT_SCHEMA, VERSION)
    r._uuid(data['result_id']); r._timestamp(data['created_at'])
    r._hash(data['source_xdw_sha256']); r._hash(data['session_sha256'])
    if (data['review_id'] != identity['review_id'] or data['coordinate_system'] != r.COORDINATES
            or data['unit'] != 'mm'):
        raise ValueError('reviewed result identity/coordinates mismatch')
    r._keys(data['validation'], 'mode identity_checked page_structure_checked')
    if (data['validation']['mode'] != 'identity' or data['validation']['identity_checked'] is not True
            or data['validation']['page_structure_checked'] is not False):
        raise ValueError('invalid reviewed validation scope')
    r._integer(data['excluded_sticky_count'], 0, 2**31 - 1)
    check_pages(data['pages'])
    page_ids, item_ids = set(), set()
    for page in data['pages']:
        r._keys(page, PAGE_KEYS); r._uuid(page['page_id'])
        if page['page_id'] in page_ids:
            raise ValueError('duplicate reviewed page ID')
        page_ids.add(page['page_id'])
        for order, item in enumerate(page['items'], 1):
            r._keys(item, ITEM_KEYS); r._uuid(item['item_id']); r._integer(item['order'], order, order)
            r._geometry(item)
            if item['item_id'] in item_ids:
                raise ValueError('duplicate reviewed item ID')
            item_ids.add(item['item_id'])
            evidence = item['origin_evidence']
            r._keys(evidence, 'status raw_base64 issues')
            if not isinstance(evidence['issues'], list):
                raise ValueError('invalid origin issues')
            for issue in evidence['issues']:
                r._keys(issue, 'index reason')
                if issue['index'] is not None:
                    r._integer(issue['index'], 0, 2**31 - 1)
                if issue['reason'] not in ('invalid', 'foreign'):
                    raise ValueError('invalid origin issue reason')
            try:
                raw = None if evidence['raw_base64'] is None else base64.b64decode(evidence['raw_base64'], validate=True)
            except (ValueError, TypeError) as exc:
                raise ValueError('invalid origin evidence') from exc
            refs, expected = origins(raw, identity, identity_hash)
            # Reconstruct classification from raw bytes; rehashing must not launder a bad reference.
            if item['origins'] != refs or evidence != expected:
                raise ValueError('origin evidence/reference mismatch')
            if item['diagnostics'] != diagnostics(item['text'], expected):
                raise ValueError('reviewed diagnostics mismatch')


def load_result(root):
    manifest_hash = r.sha256(root / 'manifest.json')
    manifest = r._manifest(root, r.RESULT_SCHEMA, r.RESULT_FILES, VERSION)
    identity = r._identity(r._read(root / 'identity.json'))
    session = r._read(root / 'session.json')
    identity_hash = manifest['files']['identity.json']
    r._validate_session(session, identity, identity_hash)
    data = r._read(root / 'reviewed.json')
    validate_result(data, identity, identity_hash)
    if (data['session_sha256'] != manifest['files']['session.json'] or
            data['source_xdw_sha256'] != manifest['files']['source-review.xdw']):
        raise ValueError('reviewed source/session hashes mismatch')
    if (root / 'reviewed.jsonl').read_bytes() != jsonl(data):
        raise ValueError('reviewed JSONL differs from canonical reviewed JSON')
    result_bytes = (root / 'reviewed.json').read_bytes()
    # Recheck fixed inputs after semantic validation, including copied identity/session.
    r._manifest(root, r.RESULT_SCHEMA, r.RESULT_FILES, VERSION)
    if (r._digest(result_bytes) != manifest['files']['reviewed.json'] or
            r.sha256(root / 'manifest.json') != manifest_hash):
        raise RuntimeError('reviewed result changed while loading')
    return r.ReviewedResult(root, manifest_hash, result_bytes)


def import_result(session_dir, edited_xdw, output_dir, *, dll_path=None):
    session = r.load_review_session(session_dir)
    edited = r._plain_path(edited_xdw)
    if edited == session.root / 'initial.xdw':
        raise ValueError('initial.xdw is an immutable baseline; explicitly submit an editable copy')
    output = r._destination(output_dir, session.root)
    identity = session.identity
    identity_hash = r._digest(session._identity_bytes)
    with r.owned_directory(output.parent, '.review-result-') as staging:
        input_hash = r._copy(edited, staging / 'source-review.xdw')
        snapshot = r._sdk(dll_path).inspect(staging / 'source-review.xdw', exclude_sticky=True)
        check_document(snapshot, identity, identity_hash); check_pages(snapshot['pages'])
        data = dict(schema=r.RESULT_SCHEMA, schema_version=VERSION, result_id=str(uuid.uuid4()),
                    review_id=session.review_id, created_at=r._now(), source_xdw_sha256=input_hash,
                    session_sha256=r._digest(session._session_bytes), coordinate_system=r.COORDINATES,
                    unit='mm', validation=dict(VALIDATION), excluded_sticky_count=snapshot['excluded_sticky_count'], pages=[])
        for page in snapshot['pages']:
            record = {key: page[key] for key in ('page', 'width_mm', 'height_mm', 'rotation')}
            record.update(page_id=str(uuid.uuid4()), items=[])
            for order, raw in enumerate(page['items'], 1):
                r._geometry(raw)
                refs, evidence = origins(raw['identity'], identity, identity_hash)
                item = {key: raw[key] for key in ('text', 'x', 'y', 'width', 'height', 'rotation', 'direction')}
                item.update(item_id=str(uuid.uuid4()), order=order, origins=refs, origin_evidence=evidence,
                            diagnostics=diagnostics(raw['text'], evidence))
                record['items'].append(item)
            data['pages'].append(record)
        (staging / 'identity.json').write_bytes(session._identity_bytes)
        (staging / 'session.json').write_bytes(session._session_bytes)
        (staging / 'reviewed.json').write_bytes(r._bytes(data))
        (staging / 'reviewed.jsonl').write_bytes(jsonl(data))
        r._write_manifest(staging, r.RESULT_SCHEMA, r.RESULT_FILES, VERSION)
        load_result(staging)
        if r.load_review_session(session.root) != session or r.sha256(edited) != input_hash:
            raise RuntimeError('review inputs changed during import')
        r.publish_new(staging, output)
    return r.load_reviewed_result(output)


def set_origins(session_dir, edited_xdw, output_xdw, assignments, *, expected_source_sha256, dll_path=None):
    session = r.load_review_session(session_dir)
    edited = r._plain_path(edited_xdw)
    r._hash(expected_source_sha256)
    output = r._destination(output_xdw, session.root)
    if output.suffix.lower() != '.xdw':
        raise ValueError('origin assignment output must be a new XDW file')
    if edited == session.root / 'initial.xdw':
        raise ValueError('initial.xdw is an immutable baseline')
    if not isinstance(assignments, list) or not assignments:
        raise ValueError('assignments must be a nonempty list')
    identity, digest = session.identity, r._digest(session._identity_bytes)
    known = {i['region_id'] for p in identity['pages'] for i in p['items']}
    with r.owned_directory(output.parent, '.review-origins-') as staging:
        target = staging / 'editable.xdw'
        input_hash = r._copy(edited, target)
        if input_hash != expected_source_sha256:
            raise ValueError('saved XDW changed; refresh page/order locators before assigning origins')
        sdk = r._sdk(dll_path)
        before = sdk.inspect(target, exclude_sticky=True)
        check_document(before, identity, digest); check_pages(before['pages'])
        expected, updates, seen = copy.deepcopy(before), [], set()
        for assignment in assignments:
            r._keys(assignment, 'page order region_ids')
            page, order, region_ids = assignment['page'], assignment['order'], assignment['region_ids']
            r._integer(page, 1, len(before['pages']))
            r._integer(order, 1, len(before['pages'][page - 1]['items']))
            if (page, order) in seen:
                raise ValueError('duplicate assignment target')
            seen.add((page, order))
            if not isinstance(region_ids, list) or any(not isinstance(i, str) or i not in known for i in region_ids):
                raise ValueError('assignment contains an unknown Canonical region')
            payload = dict(schema=ORIGIN_SCHEMA, schema_version=VERSION, review_id=session.review_id,
                           identity_sha256=digest, origins=[reference(identity, i) for i in sorted(set(region_ids))])
            raw = r._bytes(payload)
            if len(raw) > 1024 * 1024:
                raise ValueError('review attribute exceeds 1 MiB')
            updates.append(dict(page=page, order=order, raw=raw))
            expected['pages'][page - 1]['items'][order - 1]['identity'] = raw
        sdk.set_origins(target, updates)
        if sdk.inspect(target, exclude_sticky=True) != expected:
            raise RuntimeError('origin assignment did not roundtrip without changing the snapshot')
        if r.load_review_session(session.root) != session or r.sha256(edited) != input_hash:
            raise RuntimeError('review inputs changed during origin assignment')
        r.publish_new(target, output)
    return output
