"""Development-only review runner; never integrates with Portable BAT files."""
from pathlib import Path
import argparse
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'packages' / p) for p in ('docuworks-integrations', 'docuworks-ctypes')]


def main():
    parser = argparse.ArgumentParser(description='白紙Review開発検証（既存出力を上書きしません）')
    parser.add_argument('--dll', default=None)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('fixture'); p.add_argument('output'); p.add_argument('--pages', type=int, choices=(1, 2, 3), default=3); p.add_argument('--blank', action='store_true')
    p = sub.add_parser('create'); p.add_argument('run'); p.add_argument('output')
    p = sub.add_parser('import'); p.add_argument('session'); p.add_argument('edited'); p.add_argument('output')
    p = sub.add_parser('ocr'); p.add_argument('source'); p.add_argument('output'); p.add_argument('models'); p.add_argument('--cache', required=True)
    p = sub.add_parser('check'); p.add_argument('result')
    args = parser.parse_args()
    from docuworks_integrations import create_review_session, import_reviewed_result, load_reviewed_result
    if args.command == 'fixture':
        sys.path.insert(0, str(ROOT / 'packages/docuworks-integrations/tests'))
        from reviewed_fixture import create_fixture
        # This Canonical fixture is synthetic. Use its source.xdw with `ocr` for real OCR.
        result = create_fixture(args.output, args.dll, pages=args.pages, blank=args.blank)
    elif args.command == 'create':
        result = create_review_session(args.run, args.output, dll_path=args.dll)
    elif args.command == 'import':
        result = import_reviewed_result(args.session, args.edited, args.output, dll_path=args.dll)
    elif args.command == 'ocr':
        from docuworks_integrations.recognition import ocr_xdw_pages
        os.environ['DW_OCR_CACHE'] = str(Path(args.cache).resolve())
        ocr_xdw_pages(args.source, args.output, args.models, dll_path=args.dll)
        print(str(Path(args.output).resolve())); return
    else:
        result = load_reviewed_result(args.result)
        print(json.dumps(result.data, ensure_ascii=False, indent=2)); return
    print(str(result.root))


if __name__ == '__main__':
    main()
