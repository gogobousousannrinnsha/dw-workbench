"""Choose one Reviewed folder and export beside it using the public CLI."""
import argparse
from datetime import datetime
from pathlib import Path
import sys
import uuid


def choose_directory(initial):
    import tkinter as tk
    from tkinter import filedialog
    window = tk.Tk()
    try:
        window.withdraw()
        window.attributes('-topmost', True)
        return filedialog.askdirectory(parent=window, mustexist=True, initialdir=str(initial),
                                      title='校正結果を選択（reviewed.jsonのあるフォルダー）')
    finally:
        window.destroy()


def main(argv=None):
    parser = argparse.ArgumentParser(description='校正結果の全文をExcelへ出力します。')
    parser.add_argument('reviewed', nargs='?', help='Reviewedフォルダーまたはreviewed.json')
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    print('校正結果取込で作成した、reviewed.jsonのある結果フォルダーを選択してください。', flush=True)
    value = args.reviewed or choose_directory(root / 'OUTPUT' if (root / 'OUTPUT').is_dir() else root)
    if not value:
        print('キャンセルしました。')
        return 0
    from docuworks_integrations.reviewed import _plain_path
    target = _plain_path(value)
    if target.is_file() and target.name.lower() == 'reviewed.json':
        target = target.parent
    if not target.is_dir() or not (target / 'reviewed.json').is_file():
        raise ValueError('reviewed.jsonがあるReviewed結果フォルダーを指定してください。')
    output = target.parent / (target.name + '_全文_' + datetime.now().strftime('%Y%m%d-%H%M%S')
                              + '_' + uuid.uuid4().hex[:8] + '.xlsx')
    from docuworks_integrations.cli import main as cli
    return cli(['export-reviewed-xlsx', '--reviewed-dir', str(target), '--output', str(output)])


def run(argv=None):
    try:
        return main(argv)
    except (KeyboardInterrupt, EOFError):
        print('Excel出力を中断しました。', file=sys.stderr)
        return 130
    except Exception as exc:
        print(f'Excel出力に失敗しました: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(run())
