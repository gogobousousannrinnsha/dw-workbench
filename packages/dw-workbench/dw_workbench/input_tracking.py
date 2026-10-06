"""Conservative per-field ownership for OCR prefill; FieldState/schema stay v2."""
from dataclasses import asdict
import math
from .domain import Anchor, FieldState, RuleError

ORIGINS = {'initial', 'human', 'ocr', 'unknown'}


def initial_state(source, profile, field, page):
    region = profile.resolve_region(field.id, page)
    anchor = Anchor(source.id, source.sha256, region['page'], tuple(region['rect'])) if profile.matches(source, page) else None
    state = asdict(FieldState(unit=field.unit, anchor=anchor))
    if state['anchor']:
        state['anchor']['rect'] = list(state['anchor']['rect'])  # Persisted JSON coordinates.
    return state


def origins(record, source, profile):
    tracked = record['data'].get('input_tracking')
    if (isinstance(tracked, dict) and tracked.get('format') == 1 and
            tracked.get('record_revision') == record['revision'] and
            isinstance(tracked.get('fields'), dict) and
            set(tracked.get('fields', {})) == {f.id for f in profile.fields} and
            all(isinstance(value, str) and value in ORIGINS for value in tracked['fields'].values())):
        return dict(tracked['fields'])
    if tracked is not None:
        return {f.id: 'unknown' for f in profile.fields}
    # Legacy revisions do not say which field was edited. Protect every field
    # after any edit, including a deliberate clear back to the initial bytes.
    return {f.id: 'initial' if record['revision'] == 0 and
        record['data']['fields'][f.id] == initial_state(source, profile, f, record['page']) else 'unknown'
        for f in profile.fields}


def pristine(record, source, profile, field_id):
    field = next(f for f in profile.fields if f.id == field_id)
    return origins(record, source, profile)[field_id] == 'initial' and (
        record['data']['fields'][field_id] == initial_state(source, profile, field, record['page']))


def track(record, source, profile, field_id, origin):
    fields = origins(record, source, profile)
    fields[field_id] = origin
    record['data']['input_tracking'] = dict(format=1, record_revision=record['revision']+1, fields=fields)


def recognition_problem(schema, result):
    """Regions are lines of one aggregate candidate, not alternative candidates."""
    text, rows = result['text'], result['regions']
    if not rows or not isinstance(text, str) or not text.strip():
        return '文字を取得できませんでした。原文を見て入力してください'
    alternatives = result.get('alternatives', [])
    if alternatives:
        choices = {v if isinstance(v, str) else v.get('text') for v in alternatives}
        if choices != {text}:
            return '複数の認識候補があり自動選択できません。原文と候補を確認してください'
    if text.strip() != ' '.join(row['text'] for row in rows).strip():
        return '認識文字と行の結果が一致しません。原文と候補を確認してください'
    if any(not isinstance(row['confidence'], (int, float)) or not math.isfinite(row['confidence']) or
            not 0 <= row['confidence'] <= 1 for row in rows):
        return '認識結果の確かさが不正です。原文と候補を確認してください'
    try:
        schema.canonical(text)  # Validate numbers; retain exact spelling until human confirmation.
    except RuleError as exc:
        return str(exc)
    return ''
