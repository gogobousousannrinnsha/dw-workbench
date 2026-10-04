"""Deterministic rectangle selection against validated Reviewed snapshots."""
import copy
from decimal import Decimal

from .templates import JOINS, hundredths


def _number(value): return Decimal(str(value))


def _center(item, axis):
    return _number(item[axis]) + _number(item['width' if axis == 'x' else 'height']) / 2


def _inside(rectangle, item):
    return all(_number(rectangle[axis]) <= _center(item, axis) <=
               _number(rectangle[axis]) + _number(rectangle[size])
               for axis, size in (('x', 'width'), ('y', 'height')))


def reading_order(items):
    """Fixed row seeds prevent a chain of close items from drifting into one row."""
    rows = []
    for item in sorted(items, key=lambda i: (_center(i, 'y'), i['x'], i['order'])):
        for seed, members in rows:
            tolerance = min(_number(seed['height']), _number(item['height'])) / 2
            if abs(_center(item, 'y') - _center(seed, 'y')) <= tolerance:
                members.append(item)
                break
        else:
            rows.append((item, [item]))
    return [item for _, members in rows for item in sorted(members, key=lambda i: (i['x'], i['order']))]


def _extract(rectangle, page, reviewed):
    candidates = reading_order([i for i in page['items'] if _inside(rectangle, i)])
    sources = [dict(result_id=reviewed['result_id'], page=page['page'], page_id=page['page_id'],
                    item=copy.deepcopy(item)) for item in candidates]
    diagnostics = []
    if any(i['rotation'] != 0 for i in candidates): diagnostics.append('UNSUPPORTED_ROTATION')
    if any(i['direction'] != 0 for i in candidates): diagnostics.append('UNSUPPORTED_DIRECTION')
    if not candidates:
        value, status = None, 'missing'
        diagnostics.append('NO_TEXT')
    elif diagnostics:
        value, status = None, 'unsupported'
    else:
        value = JOINS[rectangle['join']].join(i['text'] for i in candidates)
        status = 'ok' if value.strip() else 'empty'
        if status == 'empty': diagnostics.append('EMPTY_TEXT')
    for item in candidates:
        evidence = item.get('origin_evidence', item.get('origin', {}))
        if evidence.get('status') in ('invalid', 'foreign', 'partial'):
            code = 'ORIGIN_' + evidence['status'].upper()
            if code not in diagnostics: diagnostics.append(code)
    result = dict(rectangle_id=rectangle['rectangle_id'], name=rectangle['name'], page=page['page'],
                  required=rectangle['required'], value=value, status=status,
                  diagnostics=diagnostics, sources=sources)
    if rectangle['purpose'] == 'condition':
        result.update(expected=rectangle['expected'],
                      matched=status == 'ok' and value.strip() == rectangle['expected'])
    return result


def evaluate(template, reviewed):
    """Inputs must already pass template/Reviewed validation; no mutation or I/O."""
    diagnostics, conditions, fields = [], [], []
    template_pages, pages = template['pages'], reviewed['pages']
    if len(template_pages) != len(pages): diagnostics.append('PAGE_COUNT_MISMATCH')
    for expected, actual in zip(template_pages, pages):
        n = expected['page']
        if any(hundredths(expected[k]) != hundredths(actual[k]) for k in ('width_mm', 'height_mm')):
            diagnostics.append(f'PAGE_SIZE_MISMATCH:{n}')
        if expected['rotation'] != actual['rotation']:
            diagnostics.append(f'PAGE_ROTATION_MISMATCH:{n}')
    if diagnostics:
        return dict(applicable=False, status='not_applicable', diagnostics=diagnostics, conditions=[], fields=[])
    for definition, page in zip(template_pages, pages):
        for rectangle in definition['rectangles']:
            if rectangle['purpose'] == 'condition': conditions.append(_extract(rectangle, page, reviewed))
    if not conditions: diagnostics.append('PAGE_ONLY_APPLICABILITY')
    if any(not condition['matched'] for condition in conditions):
        diagnostics.append('CONDITION_MISMATCH')
        return dict(applicable=False, status='not_applicable', diagnostics=diagnostics, conditions=conditions, fields=[])
    rectangles = [(rectangle, page) for definition, page in zip(template_pages, pages)
                  for rectangle in definition['rectangles'] if rectangle['purpose'] == 'field']
    rectangles.sort(key=lambda pair: (pair[0]['output_order'] is None, pair[0]['output_order'] or 0,
                                     pair[1]['page'], pair[0]['annotation_order']))
    fields = [_extract(rectangle, page, reviewed) for rectangle, page in rectangles]
    needs_review = any(field['status'] == 'unsupported' or
                       field['required'] and field['status'] in ('missing', 'empty') for field in fields)
    return dict(applicable=True, status='needs_review' if needs_review else 'ok',
                diagnostics=diagnostics, conditions=conditions, fields=fields)
