"""Lossless text CSV derived from one registered template's Structured Results."""
from collections.abc import Mapping
import csv
import json
import os
from pathlib import Path

from . import reviewed as r
from .structured import StructuredResult, load_structured_result
from ._template_messages import diagnostic_message

STATUS_LABELS = {'ok':'正常', 'needs_review':'要確認', 'not_applicable':'適用不可'}
MANAGEMENT_COLUMNS = ('文書名', '処理結果', '確認事項', '結果ID')


def _field_definitions(result):
    raw = r._plain_path(result.root/'template.json').read_bytes()
    if r._digest(raw) != result.data['template']['definition_sha256']:
        raise RuntimeError('CSV出力中にテンプレート定義が変更されました。')
    template = json.loads(raw)
    fields = [(page['page'], rect) for page in template['pages'] for rect in page['rectangles']
              if rect['purpose'] == 'field']
    fields.sort(key=lambda pair: (pair[1]['output_order'] is None, pair[1]['output_order'] or 0,
                                  pair[0], pair[1]['annotation_order']))
    return [rect for _, rect in fields]


def _headers(fields):
    names = [field['name'] for field in fields]
    reserved = set(MANAGEMENT_COLUMNS) | set(names)
    headers = []
    for name in names:
        header = name
        if header in MANAGEMENT_COLUMNS:
            while header in reserved: header = '項目:' + header
            reserved.add(header)
        headers.append(header)
    return ['文書名', '処理結果', *headers, '確認事項', '結果ID']


def _notes(data):
    notes = [diagnostic_message(code) for code in data['diagnostics']]
    for condition in data['conditions']:
        label = '適用条件' + json.dumps(condition['name'], ensure_ascii=False)
        if not condition['matched']:
            notes.append(f'{label}：不一致（期待={json.dumps(condition["expected"], ensure_ascii=False)}、'
                         f'取得={json.dumps(condition["value"], ensure_ascii=False)}）')
        notes.extend(f'{label}：{diagnostic_message(code)}' for code in condition['diagnostics'])
    for field in data['fields']:
        label = json.dumps(field['name'], ensure_ascii=False)
        notes.extend(f'{label}：{diagnostic_message(code)}' for code in field['diagnostics'])
    return ' / '.join(notes)


def _rows(results, fields, names):
    yield _headers(fields)
    for result in results:
        data = result.data
        values = {field['rectangle_id']: field['value'] for field in data['fields']}
        yield [names[result.result_id], STATUS_LABELS[data['status']],
               *['' if values.get(field['rectangle_id']) is None else values[field['rectangle_id']] for field in fields],
               _notes(data), result.result_id]


def _write_csv(path, rows):
    with path.open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream, delimiter=',', quotechar='"', quoting=csv.QUOTE_ALL, lineterminator='\r\n')
        writer.writerows(rows)
        stream.flush()
        os.fsync(stream.fileno())


def export_structured_csv(results, output_path, *, document_names) -> Path:
    """Export selected snapshots in input order, using explicit result-ID/name pairs.

    results: iterable of loaded StructuredResult objects from one registered template.
    document_names: {StructuredResult.result_id: nonempty display name}, exactly one
    entry per result. These names are user-supplied labels, not inferred provenance.
    """
    results = tuple(results)
    if not results:
        raise ValueError('CSV出力には1件以上の構造化結果が必要です。')
    if any(not isinstance(result, StructuredResult) for result in results):
        raise TypeError('StructuredResultを指定してください。')
    if not isinstance(document_names, Mapping):
        raise TypeError('文書名は結果IDと表示名の対応で指定してください。')
    names = dict(document_names)
    ids = [result.result_id for result in results]
    if len(set(ids)) != len(ids):
        raise ValueError('同じ結果IDが重複しています。')
    if set(names) != set(ids) or any(not isinstance(v, str) or not v.strip() or '\x00' in v for v in names.values()):
        raise ValueError('すべての結果IDに空でない文書名を指定してください。余分なIDは指定できません。')
    for result in results:
        if load_structured_result(result.root) != result:
            raise RuntimeError('保存された構造化結果が変更されています。')
    template = results[0].data['template']
    if any(result.data['template'] != template for result in results[1:]):
        raise ValueError('異なるテンプレート・登録版の結果は同じCSVへ出力できません。')
    output = r._destination(output_path, *(result.root for result in results))
    if output.suffix.lower() != '.csv':
        raise ValueError('出力先には.csvファイルを指定してください。')
    fields = _field_definitions(results[0])
    with r.owned_directory(output.parent, '.structured-csv-') as staging:
        temp = staging/'result.csv'
        _write_csv(temp, _rows(results, fields, names))
        for result in results:
            if load_structured_result(result.root) != result:
                raise RuntimeError('CSV出力中に構造化結果が変更されました。')
        r.publish_new(temp, output)
    return output
