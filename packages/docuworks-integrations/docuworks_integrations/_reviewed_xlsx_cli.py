"""SDK-free Reviewed Excel command boundary."""
import sys

from .reviewed import load_reviewed_result
from .reviewed_xlsx import export_reviewed_xlsx, _parts


def run(args):
    try:
        print('Reviewedを読み込んで検証しています。', flush=True)
        result = load_reviewed_result(args.reviewed_dir)
        labels = {'validate': '入力を再検証しています。', 'save': 'Excelを保存しています。',
                  'verify': '保存結果と入力の不変性を検証しています。'}
        def progress(phase, current, total):
            print(f'Excel書込: {current}/{total}ページ' if phase == 'write' else labels[phase], flush=True)
        output = export_reviewed_xlsx(result, args.output, progress=progress)
        pages = result.pages
        items = sum(len(p['items']) for p in pages)
        rows = sum(len(_parts(i['text'], i['item_id'])) for p in pages for i in p['items'])
        print(f'Excel出力完了: {len(pages)}ページ / {items}文字項目 / {rows}行')
        print(f'保存先: {output}')
        return 0
    except (KeyboardInterrupt, EOFError):
        print('Excel出力を中断しました。', file=sys.stderr)
        return 130
    except Exception as exc:
        print(f'Excel出力に失敗しました: {exc}', file=sys.stderr)
        for note in getattr(exc, '__notes__', ()):
            print(note, file=sys.stderr)
        return 1
