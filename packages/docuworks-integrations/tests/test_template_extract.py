import copy

import pytest

from docuworks_integrations._template_extract import evaluate, reading_order
from docuworks_integrations.templates import _compile
from test_templates import rectangle, snapshot, attr


def item(text='部品', x=20, y=15, order=1, **kwargs):
    return dict(item_id=f'item-{order}', order=order, text=text, x=x, y=y, width=10, height=4,
                rotation=0, direction=0, origins=[], origin_evidence=dict(status='none', raw_base64=None, issues=[]),
                diagnostics=[], **kwargs)


def fixture():
    raw = snapshot()
    raw['pages'][0]['rectangles'][1]['y'] = 50
    template = _compile(raw, '帳簿A', '0'*64)
    reviewed = dict(result_id='test-result', validation=dict(page_structure_checked=False), pages=[
        dict(page=p['page'], page_id=f'page-{p["page"]}', width_mm=p['width_mm'], height_mm=p['height_mm'],
             rotation=0, items=[]) for p in raw['pages']])
    reviewed['pages'][0]['items'] = [item(), item('番号', x=35, order=2), item(' 帳簿A\n', y=55, order=3)]
    return template, reviewed


def test_condition_and_fields_use_edited_text_and_preserve_evidence():
    t, r = fixture(); before = copy.deepcopy((t, r))
    result = evaluate(t, r)
    assert result['status'] == 'ok' and result['applicable']
    assert result['conditions'][0]['value'] == ' 帳簿A\n'
    field = result['fields'][0]
    assert field['value'] == '部品番号'
    assert [s['item']['text'] for s in field['sources']] == ['部品', '番号']
    assert (t, r) == before and r['validation']['page_structure_checked'] is False
    field['sources'][0]['item']['text'] = 'outside mutation'
    assert (t, r) == before


@pytest.mark.parametrize('text,match', [('帳簿A',True), (' \n帳簿A\t',True), ('帳簿Ａ',False), ('帳 簿A',False), ('帳簿A1',False)])
def test_exact_match_only_trims_edges(text, match):
    t, r = fixture(); r['pages'][0]['items'][-1]['text'] = text
    result = evaluate(t, r)
    assert result['applicable'] is match
    assert bool(result['fields']) is match


@pytest.mark.parametrize('mode', ['count','width','height','rotation','condition-and'])
def test_not_applicable_stops_field_extraction(mode):
    t, r = fixture()
    if mode == 'count': r['pages'].pop()
    if mode in ('width', 'height'): r['pages'][0][mode+'_mm'] += .01
    if mode == 'rotation': r['pages'][0]['rotation'] = 90
    if mode == 'condition-and':
        condition = dict(t['pages'][0]['rectangles'][1], name='追加判定', rectangle_id='p0001-a000004', annotation_order=4, expected='別の帳簿')
        t['pages'][0]['rectangles'].append(condition)
    result = evaluate(t, r)
    assert result['status'] == 'not_applicable' and not result['fields']


def test_dimensions_round_to_hundredths_not_relative_tolerance():
    t, r = fixture(); r['pages'][0]['width_mm'] += .004
    assert evaluate(t, r)['applicable']
    r['pages'][0]['width_mm'] += .001
    assert not evaluate(t, r)['applicable']


@pytest.mark.parametrize('join,expected', [('連結','部品番号'),('空白','部品 番号'),('改行','部品\n番号')])
def test_join_setting(join, expected):
    t, r = fixture(); t['pages'][0]['rectangles'][0]['join'] = join
    assert evaluate(t, r)['fields'][0]['value'] == expected


def test_inclusive_center_boundary_no_substring_clipping_and_overlaps():
    t, r = fixture(); page = r['pages'][0]
    page['items'] = [page['items'][-1], item('左端', x=5, order=2), item('右端', x=85, order=3), item('外', x=85.01, order=4)]
    t['pages'][0]['rectangles'].append(dict(t['pages'][0]['rectangles'][0], name='重なり', annotation_order=4, rectangle_id='p0001-a000004'))
    result = evaluate(t, r)
    assert [f['value'] for f in result['fields']] == ['左端右端', '左端右端']


def test_fixed_row_seed_does_not_drift_and_ties_keep_original_order():
    items = [item('A',x=30,y=10,order=1), item('B',x=10,y=12,order=2), item('C',x=0,y=14,order=3), item('D',x=10,y=12,order=4)]
    assert ''.join(i['text'] for i in reading_order(items)) == 'BDAC'
    items[1].update(height=1, y=13)
    assert reading_order(items[:2])[0]['text'] == 'A'


@pytest.mark.parametrize('mode', ['missing','empty','whitespace','rotation','direction'])
@pytest.mark.parametrize('required', [True,False])
def test_missing_empty_unsupported(mode, required):
    t, r = fixture(); t['pages'][0]['rectangles'][0]['required'] = required
    page = r['pages'][0]; page['items'].pop(1)
    if mode == 'missing': page['items'].pop(0)
    elif mode in ('empty','whitespace'): page['items'][0]['text'] = '' if mode == 'empty' else ' \n'
    else: page['items'][0][mode] = 30 if mode == 'rotation' else 1
    result = evaluate(t, r); field = result['fields'][0]
    assert field['status'] == ('missing' if mode == 'missing' else 'empty' if mode in ('empty','whitespace') else 'unsupported')
    assert result['status'] == ('needs_review' if required or mode in ('rotation','direction') else 'ok')
    assert len(field['sources']) == (0 if mode == 'missing' else 1)


@pytest.mark.parametrize('status', ['none','invalid','foreign','partial','matched'])
def test_origin_evidence_never_drops_text(status):
    t, r = fixture(); r['pages'][0]['items'][0]['origin_evidence']['status'] = status
    result = evaluate(t, r)
    assert result['fields'][0]['value'] == '部品番号'
    assert result['fields'][0]['sources'][0]['item']['origin_evidence']['status'] == status


def test_page_only_and_field_sorting():
    t, r = fixture(); rect = t['pages'][0]['rectangles'][0]
    t['pages'][0]['rectangles'] = [rect, dict(rect,name='後',annotation_order=3,rectangle_id='p0001-a000003',output_order=2),
        dict(rect,name='先',annotation_order=4,rectangle_id='p0001-a000004',output_order=1)]
    result = evaluate(t, r)
    assert result['diagnostics'] == ['PAGE_ONLY_APPLICABILITY']
    assert [f['name'] for f in result['fields']] == ['先','後','温度']
