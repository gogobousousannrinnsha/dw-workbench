"""Portable entry for a read-only Canonical OCR review report."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import uuid


def choose_directory(initial):
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    try:
        root.withdraw()
        return filedialog.askdirectory(parent=root, mustexist=True, initialdir=str(initial),
            title='元OCR結果を選択（manifest.jsonのあるフォルダー）')
    finally:
        root.destroy()


def main(argv=None):
    parser = argparse.ArgumentParser(description='元OCR結果から確認優先一覧を作成します。')
    parser.add_argument('run_dir', nargs='?')
    parser.add_argument('--threshold', type=float, default=0.8)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    portable = Path(__file__).resolve().parents[1]
    value = args.run_dir or choose_directory(portable/'OUTPUT' if (portable/'OUTPUT').is_dir() else portable)
    if not value:
        print('キャンセルしました。')
        return 0
    target = Path(value).expanduser().resolve()
    if target.is_file() and target.name == 'manifest.json':
        target = target.parent
    output = args.output or target.parent/(target.name+'_確認一覧_'+datetime.now().strftime('%Y%m%d-%H%M%S')
        +'_'+uuid.uuid4().hex[:8]+'.json')
    from docuworks_integrations.results import load_ocr_result
    from docuworks_integrations.review_report import export_review_report
    output = export_review_report(load_ocr_result(target), output, threshold=args.threshold)
    report = json.loads(output.read_text(encoding='utf-8'))
    summary = report['summary']
    print(f"確認対象: 低信頼度 {summary['low_confidence']}件 / 信頼度なし {summary['confidence_unknown']}件")
    print(f"文字未検出ページ: {summary['no_text_pages']} / 未処理ページ: {summary['unprocessed_pages']}")
    print('信頼度は認識器のスコアです。確認済みの判定ではありません。')
    for item in report['regions']:
        print(f"p{item['page']} {item['region_id']} / 信頼度 {item['confidence']} / {item['text']!r}")
    print('保存先: '+str(output))
    return 0


def run(argv=None):
    try:
        return main(argv)
    except (KeyboardInterrupt, EOFError):
        print('確認一覧の作成を中断しました。', file=sys.stderr)
        return 130
    except Exception as exc:
        print('確認一覧を作成できませんでした: '+str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(run())
