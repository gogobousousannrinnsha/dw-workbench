"""Single native job in a disposable child process. UTF-8 files carry results."""
import argparse
import json
from pathlib import Path
import traceback


def dispatch(request):
    from . import template_authoring as a
    operation = request['operation']
    args = request.get('arguments', {})
    functions = {'create': a.create_template_draft, 'refresh': a.refresh_template_draft,
                 'preview': a.preview_template_draft, 'publish': a.publish_template_draft,
                 'render': a.render_template_page}
    if operation not in functions:
        raise ValueError('未知の作成操作です。')
    value = functions[operation](**args)
    if operation in ('create', 'refresh'):
        return dict(root=str(value.root), data=value.data)
    if operation == 'publish':
        return dict(root=str(value.root), template_id=value.template_id)
    return value


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('request', type=Path)
    parser.add_argument('response', type=Path)
    args = parser.parse_args(argv)
    try:
        value = dispatch(json.loads(args.request.read_text(encoding='utf-8')))
        result = dict(ok=True, value=value)
    except Exception as exc:
        result = dict(ok=False, error=str(exc), detail=traceback.format_exc())
    with args.response.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
