"""Literal-text Excel exports of validated, immutable Reviewed snapshots."""
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

from . import reviewed as r

MAX_ROWS = 1_048_576
MAX_CELL_UNITS = 32_767
MAX_LINE_FEEDS = 253
HEADERS = ('ページ', '取得順', '本文', '分割番号', '分割総数', 'X(mm)', 'Y(mm)',
           '幅(mm)', '高さ(mm)', '書字方向', '回転(度)', '項目ID', '原本参照状態', '確認事項')
PAGE_HEADERS = ('ページ', 'ページID', '幅(mm)', '高さ(mm)', '回転(度)', '文字項目数')
INVALID_XML = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]')
NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'


def _parts(text, location):
    """Split without changing code points, CRLF pairs, or OOXML escape literals."""
    match = INVALID_XML.search(text)
    if match:
        raise ValueError(f'{location}: Excelへ出力できない文字 U+{ord(match[0]):04X} があります。')
    chunks = []
    start = index = units = feeds = 0
    while index < len(text):
        size = 2 if text.startswith('\r\n', index) else 1
        token = text[index:index + size]
        cost = 2 if size == 2 or ord(token) > 0xFFFF else 1
        new_feeds = int(token.endswith('\n'))
        if units + cost > MAX_CELL_UNITS or feeds + new_feeds > MAX_LINE_FEEDS:
            chunks.append(text[start:index])
            start = index
            units = feeds = 0
        units += cost
        feeds += new_feeds
        index += size
    chunks.append(text[start:])
    return chunks


def _write_row(sheet, row, values, formats, *, header=False):
    for col, value in enumerate(values):
        style = formats['header'] if header else formats['text'] if isinstance(value, str) else formats['number']
        if isinstance(value, str):
            # All textual fields, not just the body, are explicit literal strings.
            if len(_parts(value, f'{sheet.name}: 行{row + 1} 列{col + 1}')) != 1:
                raise ValueError(f'{sheet.name}: 行{row + 1} 列{col + 1} の文字列が長すぎます。')
            status = sheet.write_string(row, col, value, style)
        else:
            status = sheet.write_number(row, col, value, style)
        if status != 0:
            raise RuntimeError(f'Excel書込失敗: {sheet.name} 行{row + 1} 列{col + 1} ({status})')


def _verify_workbook(path, expected_rows):
    """Read the completed ZIP/XML independently of the writer, bounded by one row."""
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('ExcelファイルのZIP検証に失敗しました。')
        actual = {}
        for name in archive.namelist():
            if not name.endswith(('.xml', '.rels')):
                continue
            count = 0
            sheet_data = None
            with archive.open(name) as stream:
                for event, element in ET.iterparse(stream, events=('start', 'end')):
                    if event == 'start' and element.tag == NS + 'sheetData':
                        sheet_data = element
                    if event != 'end':
                        continue
                    if element.tag in (NS + 'f', NS + 'hyperlink'):
                        raise RuntimeError('本文出力に数式またはリンクが含まれています。')
                    if element.tag == NS + 'row':
                        count += 1
                        if int(element.attrib['r']) != count:
                            raise RuntimeError('Excel出力の行が連続していません。')
                        if sheet_data is not None:
                            sheet_data.remove(element)
                        element.clear()
            if name.startswith('xl/worksheets/sheet'):
                actual[name] = count
        if actual != expected_rows:
            raise RuntimeError('Excel出力の行数が一致しません。')


def export_reviewed_xlsx(result: r.ReviewedResult, output_path, *, progress=None) -> Path:
    """Create one new XLSX; progress(phase, current, total) must not mutate input.

    Phases are validate, write, save, verify. Completion belongs to the caller,
    after publication and cleanup have succeeded. No SDK, OCR or Excel process.
    """
    if not isinstance(result, r.ReviewedResult):
        raise TypeError('ReviewedResultを指定してください。')
    if progress is not None and not callable(progress):
        raise TypeError('progressには呼び出し可能な関数を指定してください。')
    def report(phase, current=0, total=0):
        if progress is not None:
            progress(phase, current, total)
    report('validate')
    if r.load_reviewed_result(result.root) != result:
        raise RuntimeError('保存されたReviewedが変更されています。')
    output = r._destination(output_path, result.root)
    if output.suffix.lower() != '.xlsx':
        raise ValueError('出力先には.xlsxファイルを指定してください。')
    try:
        import xlsxwriter
    except ImportError as exc:
        raise RuntimeError('Excel出力ライブラリがありません。docuworks-integrations[xlsx]を導入するか、Portableの修復BATを実行してください。') from exc
    from . import __version__
    data = result.data  # The accessor decodes the snapshot. Do this only once.
    pages = data['pages']
    item_count = sum(len(page['items']) for page in pages)
    expected_rows = {}
    with r.owned_directory(output.parent, '.reviewed-xlsx-') as staging:
        temp = staging / 'result.xlsx'
        book = xlsxwriter.Workbook(temp, {
            'constant_memory': True, 'tmpdir': str(staging),
            'strings_to_numbers': False, 'strings_to_formulas': False, 'strings_to_urls': False,
        })
        try:
            book.set_properties({'title': 'Reviewed 全文一覧', 'author': 'DW-OCR',
                                 'comments': 'ページ内取得順は文章の読み順ではありません。'})
            formats = {
                'header': book.add_format({'bold': True, 'bg_color': '#DCE6F1', 'text_wrap': True, 'valign': 'top'}),
                'text': book.add_format({'num_format': '@', 'text_wrap': True, 'valign': 'top'}),
                'number': book.add_format({'valign': 'top'}),
            }
            sheet_index = 0
            def new_body_sheet():
                nonlocal sheet_index
                sheet_index += 1
                sheet = book.add_worksheet('全文一覧' if sheet_index == 1 else f'全文一覧_{sheet_index}')
                sheet.freeze_panes(1, 2)
                sheet.set_column(0, 1, 9)
                sheet.set_column(2, 2, 70)
                sheet.set_column(3, 10, 12)
                sheet.set_column(11, 11, 38)
                sheet.set_column(12, 13, 24)
                _write_row(sheet, 0, HEADERS, formats, header=True)
                return sheet
            def finish_body(sheet, rows):
                if rows > 1:
                    sheet.autofilter(0, 0, rows - 1, len(HEADERS) - 1)
                expected_rows[f'xl/worksheets/sheet{sheet_index}.xml'] = rows
            body = new_body_sheet()
            row = 1
            output_rows = 0
            for page in pages:
                for item in page['items']:
                    location = f"ページ{page['page']} 項目{item['order']} ({item['item_id']})"
                    chunks = _parts(item['text'], location)
                    origin = item['origin_evidence']['status'] if 'origin_evidence' in item else item['origin']['status']
                    for part, text in enumerate(chunks, 1):
                        if row >= MAX_ROWS:
                            finish_body(body, row)
                            body = new_body_sheet()
                            row = 1
                        values = (page['page'], item['order'], text, part, len(chunks),
                                  item['x'], item['y'], item['width'], item['height'],
                                  '縦書き' if item['direction'] else '横書き', item['rotation'],
                                  item['item_id'], origin, ' / '.join(item['diagnostics']))
                        body.set_row(row, min(90, 15 * max(1, text.count('\n') + 1)))
                        _write_row(body, row, values, formats)
                        row += 1
                        output_rows += 1
                report('write', page['page'], len(pages))
            finish_body(body, row)
            info = book.add_worksheet('文書・ページ情報')
            info.set_column(0, 0, 27)
            info.set_column(1, 1, 72)
            info.set_column(2, 5, 15)
            validation = ('ID照合済み／ページ構造未検証' if data['schema_version'] == '2.0'
                          else '旧形式1.0の検証契約（文書・ページ構造照合）')
            metadata = [
                ('項目', '値'), ('Reviewedフォルダー名', result.root.name),
                ('結果ID', data['result_id']), ('Review ID', data['review_id']),
                ('Reviewed形式', data['schema_version']), ('取込日時', data['created_at']),
                ('出力日時(UTC)', datetime.now(timezone.utc).isoformat()),
                ('Reviewed manifest SHA-256', result.manifest_sha256),
                ('取込元XDW SHA-256', data['source_xdw_sha256']),
                ('検証情報', validation), ('除外した付箋数', data.get('excluded_sticky_count', '記録なし')),
                ('全ページ数', len(pages)), ('文字項目数', item_count), ('出力本文行数', output_rows),
                ('出力プログラム', f'DW-OCR Integrations {__version__} / XlsxWriter {xlsxwriter.__version__}'),
                ('本文の範囲', 'Reviewedに収録された通常テキスト全件。付箋・画像・元の書式の再現は対象外。'),
                ('並び順', 'ページ→取得順→分割番号。取得順は文章の読み順ではありません。'),
                ('長文', '同じ項目IDの本文を分割番号順に区切りを加えず連結すると元の文字列になります。'),
                ('表示', 'セルの表示高には上限があります。長い本文は数式バーでも確認してください。'),
            ]
            if len(metadata) + 1 + len(pages) > MAX_ROWS:
                raise ValueError('ページ情報がExcelの行数上限を超えます。')
            for index, values in enumerate(metadata):
                _write_row(info, index, values, formats, header=index == 0)
            page_header = len(metadata)
            _write_row(info, page_header, PAGE_HEADERS, formats, header=True)
            info.freeze_panes(page_header + 1, 0)
            for index, page in enumerate(pages, page_header + 1):
                _write_row(info, index, (page['page'], page['page_id'], page['width_mm'],
                           page['height_mm'], page['rotation'], len(page['items'])), formats)
            expected_rows[f'xl/worksheets/sheet{sheet_index + 1}.xml'] = page_header + 1 + len(pages)
            report('save')
            book.close()
        finally:
            # Release handles even when ZIP assembly raises. Never retry close().
            for sheet in book.worksheets():
                if sheet.row_data_fh is not None and not sheet.row_data_fh.closed:
                    sheet.row_data_fh.close()
        report('verify')
        _verify_workbook(temp, expected_rows)
        with temp.open('r+b') as stream:
            os.fsync(stream.fileno())
        if r.load_reviewed_result(result.root) != result:
            raise RuntimeError('Excel出力中にReviewedが変更されました。')
        # Recheck path guards just before publication, including newly created output.
        r._destination(output, result.root)
        r.publish_new(temp, output)
    return output
