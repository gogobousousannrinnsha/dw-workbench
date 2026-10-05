"""Portable folder picker for the existing, one-document apply-template CLI."""
import argparse
from datetime import datetime
from pathlib import Path
import sys
import uuid


def choose_directory(title, initial):
    import tkinter as tk
    from tkinter import filedialog

    window = tk.Tk()
    try:
        window.withdraw()
        window.attributes('-topmost', True)
        return filedialog.askdirectory(
            parent=window, title=title, initialdir=str(initial), mustexist=True,
        )
    finally:
        window.destroy()


def result_directory(value, filename, label):
    path = Path(value).absolute()
    if path.is_file() and path.name.lower() == filename:
        path = path.parent
    if not path.is_dir() or not (path / filename).is_file():
        raise ValueError(f'{label}は{filename}が入ったフォルダーを指定してください：{path}')
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='校正結果へ登録済みテンプレートを適用します。省略した入力は選択画面で指定します。',
    )
    parser.add_argument('reviewed', nargs='?', help='reviewed.jsonがある校正結果フォルダー')
    parser.add_argument('template', nargs='?', help='template.jsonがある登録済みテンプレートの版フォルダー')
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    print('校正結果から項目を抽出します。', flush=True)
    print('校正結果：校正結果取込で作成したreviewed.jsonのあるフォルダー', flush=True)
    print('テンプレート：templates内の登録版（例：帳簿A / v001）', flush=True)

    reviewed_value = args.reviewed or choose_directory(
        '校正結果を選択（reviewed.jsonのあるフォルダー）',
        root / 'OUTPUT' if (root / 'OUTPUT').is_dir() else root,
    )
    if not reviewed_value:
        print('キャンセルしました。')
        return 0
    reviewed = result_directory(reviewed_value, 'reviewed.json', '校正結果')
    template_value = args.template or choose_directory(
        '登録済みテンプレートの版を選択（template.jsonのあるフォルダー）',
        root / 'templates' if (root / 'templates').is_dir() else root,
    )
    if not template_value:
        print('キャンセルしました。')
        return 0
    template = result_directory(template_value, 'template.json', 'テンプレート')

    from docuworks_integrations.cli import main as apply_cli

    parent = root / 'structured'
    parent.mkdir(exist_ok=True)
    output = parent / ('result-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    print(f'校正結果：{reviewed}\nテンプレート：{template}', flush=True)
    code = apply_cli([
        'apply-template', '--template-dir', str(template),
        '--reviewed-dir', str(reviewed), '--output-dir', str(output),
    ])
    if code in (0, 2):
        print('抽出結果ファイル：' + str(output / 'structured.json'))
        if code == 2:
            print('要確認または適用不可の結果を保存しました。上の判定・確認事項を確認してください。')
    else:
        print('抽出に失敗しました。上のエラーを確認してください。', file=sys.stderr)
    return code


def run(argv=None):
    try:
        return main(argv)
    except (KeyboardInterrupt, EOFError):
        print('中断しました。', file=sys.stderr)
        return 130
    except Exception as exc:
        print(f'抽出に失敗しました：{exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(run())
