from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


def read_image_size(path):
    from .opencv import read_image_size as implementation
    return implementation(path)



def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="docuworks-integrations")
    subparsers = parser.add_subparsers(dest="command", required=True)
    annotate = subparsers.add_parser("annotate-image")
    annotate.add_argument("--image", required=True, type=Path)
    annotate.add_argument("--regions-json", required=True, type=Path)
    annotate.add_argument("--page-width-mm", required=True, type=float)
    annotate.add_argument("--page-height-mm", required=True, type=float)
    annotate.add_argument("--page", type=int, default=1)
    annotate.add_argument("--input-xdw", required=True, type=Path)
    annotate.add_argument("--output-xdw", required=True, type=Path)
    annotate.add_argument("--confidence-threshold", type=float, default=0.0)
    annotate.add_argument("--font-size", type=float, default=12.0)
    annotate.add_argument("--dll-path", type=Path)
    annotate.add_argument("--codepage", type=int)
    annotate.add_argument("--dry-run", action="store_true")
    annotate.add_argument("--report", type=Path)
    ocr = subparsers.add_parser("ocr-xdw")
    ocr.add_argument("--input-xdw", required=True, type=Path)
    ocr.add_argument("--run-dir", required=True, type=Path)
    ocr.add_argument("--model-root", required=True, type=Path)
    selection = ocr.add_mutually_exclusive_group()
    selection.add_argument("--page", type=int)
    selection.add_argument("--pages")
    selection.add_argument("--all-pages", action="store_true")
    ocr.add_argument("--dpi", type=int, choices=(300, 600), default=300)
    ocr.add_argument("--dll-path", type=Path)
    folder = subparsers.add_parser("ocr-folder")
    folder.add_argument("--input-dir", required=True, type=Path)
    folder.add_argument("--batch-dir", required=True, type=Path)
    folder.add_argument("--model-root", required=True, type=Path)
    folder.add_argument("--recursive", action="store_true")
    folder.add_argument("--dpi", type=int, choices=(300, 600), default=300)
    folder.add_argument("--dll-path", type=Path)
    mark = subparsers.add_parser("mark-region")
    mark.add_argument("--run-dir", required=True, type=Path)
    mark.add_argument("--region-id", required=True)
    mark.add_argument("--input-xdw", type=Path)
    mark.add_argument("--output-xdw", required=True, type=Path)
    mark.add_argument("--dry-run", action="store_true")
    mark.add_argument("--dll-path", type=Path)
    convert = subparsers.add_parser("convert-ocr-run")
    convert.add_argument("--run-dir", required=True, type=Path)
    convert.add_argument("--output-dir", required=True, type=Path)
    export = subparsers.add_parser("export-ocr")
    export.add_argument("--run-dir", required=True, type=Path)
    export.add_argument("--format", required=True, choices=("jsonl",))
    export.add_argument("--output", required=True, type=Path)
    rectangles = subparsers.add_parser('annotate-rectangles')
    rectangles.add_argument('--run-dir', required=True, type=Path)
    rectangles.add_argument('--output-xdw', required=True, type=Path)
    rectangles.add_argument('--input-xdw', type=Path)
    rectangles.add_argument('--dll-path', type=Path)
    rectangles.add_argument('--dry-run', action='store_true')
    rectangles.add_argument('--padding-mm', type=float, default=.5)
    rectangles.add_argument('--min-confidence', type=float, default=0.)
    rectangles.add_argument('--color', default='red')
    maps = subparsers.add_parser('render-text-maps')
    maps.add_argument('--run-dir', required=True, type=Path)
    maps.add_argument('--output-dir', required=True, type=Path)
    maps.add_argument('--font', type=Path)
    maps.add_argument('--min-confidence', type=float, default=0.)
    maps.add_argument('--page', type=int)
    process = subparsers.add_parser('process-documents')
    process.add_argument('inputs', nargs='+', type=Path)
    process.add_argument('--output-dir', required=True, type=Path)
    process.add_argument('--runs-dir', required=True, type=Path)
    process.add_argument('--model-root', required=True, type=Path)
    process.add_argument('--settings', type=Path)
    process.add_argument('--dll-path', type=Path)
    register = subparsers.add_parser('register-template', help='矩形XDWをテンプレートとして登録')
    register.add_argument('--template-xdw', required=True, type=Path)
    register.add_argument('--output-dir', required=True, type=Path)
    register.add_argument('--name')
    register.add_argument('--dll-path', type=Path)
    check = subparsers.add_parser('check-template', help='登録内容と適用結果を保存せず確認')
    check.add_argument('--template-dir', required=True, type=Path)
    check.add_argument('--reviewed-dir', type=Path)
    apply = subparsers.add_parser('apply-template', help='テンプレートを適用して構造化結果を保存')
    apply.add_argument('--template-dir', required=True, type=Path)
    apply.add_argument('--reviewed-dir', required=True, type=Path)
    apply.add_argument('--output-dir', required=True, type=Path)
    editor = subparsers.add_parser('template-editor', help='テンプレート作成画面を開く')
    editor.add_argument('--app-root', required=True, type=Path,
                        help='templatesとtemplate-draftsを保存するPortableフォルダー')
    csv_export = subparsers.add_parser('export-structured-csv', help='同じテンプレートの構造化結果をCSVへ出力')
    csv_export.add_argument('--entry', action='append', nargs=2, required=True,
                            metavar=('RESULT_DIR', 'DOCUMENT_NAME'), help='結果フォルダーと文書名。文書ごとに繰り返し指定')
    csv_export.add_argument('--output', required=True, type=Path)
    xlsx_export = subparsers.add_parser('export-reviewed-xlsx', help='校正結果の通常テキスト全文をExcelへ出力')
    xlsx_export.add_argument('--reviewed-dir', required=True, type=Path)
    xlsx_export.add_argument('--output', required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ('template-editor', 'register-template', 'check-template', 'apply-template', 'export-structured-csv', 'export-reviewed-xlsx', '--help', '-h'):
        # Windows CI/redirection may default to cp1252, which cannot print Japanese.
        # Scope this output contract to the new commands and the shared help text.
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, 'reconfigure') and not stream.isatty():
                stream.reconfigure(encoding='utf-8')
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == 'export-reviewed-xlsx':
        from ._reviewed_xlsx_cli import run
        return run(args)
    if args.command == 'template-editor':
        from .template_editor import launch
        return launch(args.app_root)
    if args.command == 'export-structured-csv':
        from ._structured_csv_cli import run
        return run(args)
    if args.command in ('register-template', 'check-template', 'apply-template'):
        from ._template_cli import run
        return run(args)
    if args.command in ('annotate-rectangles','render-text-maps','process-documents'):
        values = vars(args).copy(); command = values.pop('command')
        if command == 'annotate-rectangles':
            from .derivatives import annotate_rectangles
            payload = annotate_rectangles(**values)
        elif command == 'render-text-maps':
            from .derivatives import render_text_maps
            payload = render_text_maps(**values)
        else:
            from .jobs import process_documents
            from .settings import load_settings
            values['settings'] = load_settings(values['settings']) if values['settings'] else None
            payload = process_documents(**values)
        print(json.dumps(payload,ensure_ascii=False,indent=2))
        return payload.get('exit_code',0)
    if args.command == "ocr-folder":
        from .batch import ocr_folder
        try:
            result = ocr_folder(args.input_dir, args.batch_dir, args.model_root,
                recursive=args.recursive, dpi=args.dpi, dll_path=args.dll_path)
        except (ValueError, FileExistsError, NotADirectoryError) as exc:
            parser.error(str(exc))
        except KeyboardInterrupt:
            return 130
        except Exception as exc:
            print(f"Batch failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return result.exit_code
    if args.command == "convert-ocr-run":
        from .legacy_results import convert_ocr_run
        result = convert_ocr_run(args.run_dir, args.output_dir)
        print(json.dumps({"run_id": result.run_id, "output_dir": str(result.root)}))
        return 0
    if args.command == "export-ocr":
        from .results import load_ocr_result, export_jsonl
        print(export_jsonl(load_ocr_result(args.run_dir), args.output))
        return 0
    if args.command in ("ocr-xdw", "mark-region"):
        if args.command == "ocr-xdw":
            from .recognition import ocr_xdw_pages
            from .page_selection import parse_pages
            pages = None if args.all_pages else parse_pages(args.pages) if args.pages is not None else (args.page if args.page is not None else 1,)
            payload = ocr_xdw_pages(args.input_xdw, args.run_dir, args.model_root, pages=pages, dpi=args.dpi, dll_path=args.dll_path)
        else:
            from .consumers import mark_region
            payload = mark_region(args.run_dir, args.region_id, args.output_xdw, dry_run=args.dry_run, dll_path=args.dll_path, input_xdw=args.input_xdw)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.command != "annotate-image":
        raise AssertionError(args.command)
    if args.dry_run and args.report is not None:
        raise ValueError("--dry-run writes JSON only to stdout; --report is not allowed")
    from .executor import execute_plan
    from .ocr import JsonOcrEngine
    from .planning import build_ocr_plan
    from .transforms import PageTransform
    width, height = read_image_size(args.image)
    transform = PageTransform(width, height, args.page_width_mm, args.page_height_mm)
    plan = build_ocr_plan(
        args.image,
        JsonOcrEngine(args.regions_json),
        transform,
        page=args.page,
        confidence_threshold=args.confidence_threshold,
        font_size=args.font_size,
    )
    report = execute_plan(
        plan,
        args.input_xdw,
        args.output_xdw,
        dry_run=args.dry_run,
        dll_path=args.dll_path,
        codepage=args.codepage,
    )
    payload = {"plan": plan.to_dict(), "execution": report.to_dict()}
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    print(rendered)
    if args.report is not None:
        report_path = args.report.expanduser().resolve()
        if report_path.exists():
            raise FileExistsError(report_path)
        report_path.write_text(rendered + "\n", encoding="utf-8")
    return 0
