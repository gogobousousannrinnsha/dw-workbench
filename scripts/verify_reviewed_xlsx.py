"""Reproducible synthetic large-bundle/export checks, isolated from user documents."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import threading
import time


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def create_fixture(repo, folder, page_count=256, item_count=100000):
    sys.path.insert(0, str(repo / 'packages/docuworks-integrations'))
    sys.path.insert(0, str(repo / 'packages/docuworks-integrations/tests'))
    import pytest
    from test_reviewed_v2 import modern, take
    from test_reviewed import read, write
    folder.mkdir(parents=True, exist_ok=False)
    with pytest.MonkeyPatch.context() as patch:
        _, session, _ = modern(folder, patch)
        data = read(session.review_xdw)
        seed_page = data['pages'][0]
        seed_item = seed_page['items'][0]
        pages = []
        number = 0
        for page in range(1, page_count + 1):
            entry = copy.deepcopy(seed_page)
            entry.update(page=page, items=[])
            for local in range(item_count // page_count + (page <= item_count % page_count)):
                number += 1
                entry['items'].append(dict(seed_item, identity=None,
                    text=f'{number:08d} 校正済み本文 𠮷😀\r\n=1+2\n前後空白あり ',
                    x=5 + local % 10 * 15, y=5 + local // 10 * 5))
            pages.append(entry)
        data['pages'] = pages
        write(session.review_xdw, data)
        result = take(session, folder / 'reviewed-synthetic')
        assert len(result.pages) == page_count
    description = dict(synthetic=True, native_sdk_used=False, pages=page_count, items=item_count,
                       reviewed_dir=str(result.root), source='synthetic SDK boundary; not a real XDW document')
    (folder / 'fixture.json').write_text(json.dumps(description, indent=2) + '\n', encoding='utf-8')
    return description


def verify_export(result_dir, output, report_path, reader_libs):
    # Import installed application before adding test-only independent reader libraries.
    import docuworks_integrations
    from docuworks_integrations import load_reviewed_result, export_reviewed_xlsx
    import psutil
    before = {p.name: sha(p) for p in result_dir.iterdir() if p.is_file()}
    process = psutil.Process()
    peak = [process.memory_info().rss]
    stop = threading.Event()
    def sample():
        while not stop.wait(.1):
            peak[0] = max(peak[0], process.memory_info().rss)
    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    started = time.perf_counter()
    phases = []
    try:
        result = load_reviewed_result(result_dir)
        loaded = time.perf_counter()
        def progress(phase, current, total):
            phases.append(dict(phase=phase, current=current, total=total, elapsed=time.perf_counter() - started))
            if phase != 'write' or current % 32 == 0 or current == total:
                print(f'{phase} {current}/{total}', flush=True)
        export_reviewed_xlsx(result, output, progress=progress)
        exported = time.perf_counter()
    finally:
        peak[0] = max(peak[0], process.memory_info().rss)
        stop.set()
        thread.join()
    # Reader imports are intentionally excluded from exporter memory measurements.
    sys.path.insert(0, str(reader_libs))
    import openpyxl
    book = openpyxl.load_workbook(output, read_only=True, data_only=False)
    try:
        expected = ((page, item) for page in result.pages for item in page['items'])
        current = next(expected, None)
        chunks = []
        items = rows = 0
        for sheet in book:
            if not sheet.title.startswith('全文一覧'):
                continue
            for row in sheet.iter_rows(min_row=2):
                assert current is not None
                page, item = current
                values = [cell.value for cell in row]
                assert values[0:2] == [page['page'], item['order']]
                assert values[5:9] == [item[k] for k in ('x', 'y', 'width', 'height')]
                assert values[9:12] == ['縦書き' if item['direction'] else '横書き', item['rotation'], item['item_id']]
                assert row[2].data_type in ('s', 'inlineStr') and all(cell.data_type != 'f' for cell in row)
                text = re.sub(r'_x([0-9a-fA-F]{4})_', lambda m: chr(int(m[1], 16)), values[2] or '')
                chunks.append(text)
                assert values[3] == len(chunks)
                rows += 1
                if values[3] == values[4]:
                    assert ''.join(chunks) == item['text']
                    chunks.clear()
                    items += 1
                    current = next(expected, None)
        assert current is None and not chunks
        info_rows = list(book['文書・ページ情報'].values)
        actual_pages = [row for row in info_rows if isinstance(row[0], int)]
        assert len(actual_pages) == len(result.pages)
        for row, page in zip(actual_pages, result.pages):
            assert row == (page['page'], page['page_id'], page['width_mm'], page['height_mm'], page['rotation'], len(page['items']))
    finally:
        book.close()
    assert before == {p.name: sha(p) for p in result_dir.iterdir() if p.is_file()}
    report = dict(pages=len(result.pages), items=items, output_rows=rows, all_text_and_geometry_equal=True,
                  input_unchanged=True, load_seconds=loaded - started, export_seconds=exported - loaded,
                  load_export_seconds=exported - started, sampled_process_peak_rss_bytes=peak[0],
                  sampling_ms=100, memory_scope='current process through loading and export; reader excluded',
                  output_bytes=output.stat().st_size, output_sha256=sha(output),
                  package=docuworks_integrations.__file__, version=docuworks_integrations.__version__, phases=phases)
    report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return {k: v for k, v in report.items() if k != 'phases'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('create')
    create.add_argument('--repo', required=True, type=Path)
    create.add_argument('--folder', required=True, type=Path)
    export = commands.add_parser('export')
    export.add_argument('--reviewed', required=True, type=Path)
    export.add_argument('--output', required=True, type=Path)
    export.add_argument('--report', required=True, type=Path)
    export.add_argument('--reader-libs', required=True, type=Path)
    args = parser.parse_args()
    result = create_fixture(args.repo, args.folder) if args.command == 'create' else verify_export(
        args.reviewed, args.output, args.report, args.reader_libs)
    print(json.dumps(result, ensure_ascii=False), flush=True)
