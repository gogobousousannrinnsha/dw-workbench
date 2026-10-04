"""Japanese terminal summaries for template registration and application."""
import json
import sys

from . import templates as t
from . import reviewed as r
from . import structured as s
from ._template_extract import evaluate
from ._template_messages import LABELS, diagnostic_message


def _quote(value): return json.dumps(value, ensure_ascii=False)


def _diagnostics(codes):
    for code in codes:
        print('  ' + diagnostic_message(code))


def _summary(data, *, fields=True):
    print('判定：' + LABELS[data['status']])
    _diagnostics(data['diagnostics'])
    for condition in data['conditions']:
        print(f'条件 {_quote(condition["name"])}：' + ('一致' if condition['matched'] else '不一致') +
              f' 取得={_quote(condition["value"])} 期待={_quote(condition["expected"])}')
        _diagnostics(condition['diagnostics'])
    if fields:
        for field in data['fields']:
            print(f'{_quote(field["name"])}：{_quote(field["value"])}（{LABELS[field["status"]]}）')
            _diagnostics(field['diagnostics'])


def run(args):
    try:
        if args.command == 'register-template':
            template = t.register_rectangle_template(args.template_xdw, args.output_dir, name=args.name, dll_path=args.dll_path)
            print(f'テンプレートを登録しました：{_quote(template.data["name"])}\n保存先：{template.root}')
            if not any(rect['purpose'] == 'condition' for page in template.data['pages'] for rect in page['rectangles']):
                _diagnostics(['PAGE_ONLY_APPLICABILITY'])
            return 0
        if args.command == 'check-template':
            template = t.load_rectangle_template(args.template_dir)
            print(f'テンプレート：{_quote(template.data["name"])}（{len(template.data["pages"])}ページ）')
            for page in template.data['pages']:
                for rect in page['rectangles']:
                    print(f'  ページ{page["page"]}：{_quote(rect["name"])}（{"取得" if rect["purpose"] == "field" else "適用判定"}）')
            if args.reviewed_dir is None:
                if not any(rect['purpose'] == 'condition' for page in template.data['pages'] for rect in page['rectangles']):
                    _diagnostics(['PAGE_ONLY_APPLICABILITY'])
                return 0
            data = evaluate(template.data, r.load_reviewed_result(args.reviewed_dir).data)
            _summary(data)
            return 0 if data['status'] == 'ok' else 2
        result = s.apply_rectangle_template(args.template_dir, args.reviewed_dir, args.output_dir)
        _summary(result.data)
        print(f'保存先：{result.root}')
        return 0 if result.data['status'] == 'ok' else 2
    except Exception as exc:
        # Native SDK errors have their own base class; this is the terminal boundary.
        print(f'処理できませんでした：{exc}', file=sys.stderr)
        return 1
