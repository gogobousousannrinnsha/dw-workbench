"""CSV export CLI boundary; no native or spreadsheet dependencies."""
from collections import Counter
import sys

from .structured import load_structured_result
from .structured_csv import export_structured_csv, STATUS_LABELS


def run(args):
    try:
        results = [load_structured_result(path) for path, _ in args.entry]
        names = {result.result_id: name for result, (_, name) in zip(results, args.entry)}
        output = export_structured_csv(results, args.output, document_names=names)
        counts = Counter(result.data['status'] for result in results)
        print(f'CSVを出力しました：{len(results)}件')
        print(' / '.join(f'{label}：{counts[status]}件' for status, label in STATUS_LABELS.items()))
        print(f'保存先：{output}')
        return 2 if counts['needs_review'] or counts['not_applicable'] else 0
    except (OSError, ValueError, RuntimeError, TypeError) as exc:
        print(f'CSVを出力できませんでした：{exc}', file=sys.stderr)
        return 1
