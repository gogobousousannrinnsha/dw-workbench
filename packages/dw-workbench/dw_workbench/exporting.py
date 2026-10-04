"""Frozen dataset export. Each file is independently staged, verified and recorded."""
from decimal import Decimal
from pathlib import Path
import csv
import io
import itertools
import json
import math
import os
import posixpath
import re
import zipfile
from xml.etree import ElementTree as ET
from .domain import RuleError, Status, identifier, timestamp
from .storage import atomic_bytes, digest, FileLock

XML = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
OFFICE_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
RESULT_METADATA = ["文書名", "原本ID", "記録単位", "元ページ番号", "記録ID", "テンプレート名", "テンプレートID", "テンプレート版"]
EVIDENCE_V2_HEADER = ["結果シート", "項目定義ID", "項目定義版", *RESULT_METADATA, "項目ID", "項目名", "原文", "採用値", "単位", "確認状態", "理由・診断", "原本ハッシュ", "原本相対パス", "根拠ページ", "X mm", "Y mm", "幅 mm", "高さ mm", "確認した版", "確定した版", "ページ割当版"]
STATUS_LABELS = {"missing": "未取得", "pending": "未確認", "accepted": "確認済み", "deferred": "保留", "not_applicable": "対象外"}


def literal(text):
    text = str(text)
    # Check UTF-16 length conservatively, including supplementary characters.
    if len(text.encode("utf-16-le"))//2 > 32767 or text.count("\n") > 253:
        raise RuleError("Excelの文字数・改行数上限を超えています。CSVをご利用ください")
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", text):
        raise RuleError("Excelに書けない制御文字があります。原文を訂正してください")
    return text


def excel_number(value):
    decimal = Decimal(value)
    normalized = decimal.normalize()
    if len(normalized.as_tuple().digits) > 15:
        return None, "Excelの15桁精度を超えるため文字列"
    number = float(decimal)
    if not math.isfinite(number) or (decimal and not number):
        return None, "Excel数値範囲外のため文字列"
    # Excel also flushes very small normalized numbers; ensure decimal round trip.
    if number and abs(number) < 2.2250738585072014e-308:
        return None, "Excel数値範囲外のため文字列"
    if Decimal(format(number, ".15g")) != decimal:
        return None, "Excelで十進精度を保持できないため文字列"
    return number, ""


def result_rows(group):
    fields = group["profile"]["fields"]
    header = ["文書名", "記録ID"]
    for f in fields:
        header.extend([f["name"], f["name"]+" 単位"])
    rows = []
    for r in group["records"]:
        values = [r["source"]["name"], r["id"]]
        for f in fields:
            s = r["fields"][f["id"]]
            values.extend([s["value"] if s["status"] == Status.ACCEPTED else "", s["unit"]])
        rows.append(values)
    return header, rows


def write_csv(path, group):
    header, rows = result_rows(group)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)
        stream.flush()
        os.fsync(stream.fileno())
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        actual = list(csv.reader(stream))
    if actual != [header, *rows] or not path.read_bytes().startswith(b"\xef\xbb\xbf"):
        raise RuleError("CSVの再読込検証に失敗しました")


def _strings(values):
    return [("s", str(value)) for value in values]


def _record_metadata(record):
    page = record.get("page")
    profile = record["profile"]
    return [record["source"]["name"], record["source"]["id"], "ページ" if page is not None else "文書",
        page if page is not None else "", record["id"], profile["name"], profile["id"], profile["version"]]


def _field_value(state):
    return state["value"] if state["status"] == Status.ACCEPTED else ""


def _number_and_reason(field, state):
    value = _field_value(state)
    return excel_number(value) if value and field["kind"] == "decimal" else (None, "")


def result_rows_v2(group, numeric=False):
    """Yield typed rows from a frozen schema table, without copying all values."""
    fields = group["schema"]["fields"]
    header = list(RESULT_METADATA)
    for field in fields:
        header.extend([field["name"], field["name"]+" 単位"])
    yield _strings(header)
    for record in group["records"]:
        row = _strings(_record_metadata(record))
        if numeric and record.get("page") is not None:
            row[3] = ("n", record["page"])
        for field in fields:
            state = record["fields"][field["id"]]
            value = _field_value(state)
            number, _ = _number_and_reason(field, state) if numeric else (None, "")
            row.append(("n", number) if number is not None else ("s", value))
            row.append(("s", state["unit"]))
        yield row


def write_csv_v2(path, group):
    longest = 0
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        for row in result_rows_v2(group):
            values = [value for _, value in row]
            longest = max(longest, *(len(value) for value in values))
            writer.writerow(values)
        stream.flush()
        os.fsync(stream.fileno())
    # Re-read incrementally with the standard library parser, independent of the writer.
    with path.open("rb") as stream:
        if stream.read(3) != b"\xef\xbb\xbf":
            raise RuleError("CSVにUTF-8 BOMがありません")
    # CSV remains available for text exceeding Excel's cell limit. Raise the
    # parser's process-local read limit monotonically to cover the written data.
    csv.field_size_limit(max(csv.field_size_limit(), longest))
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        for expected, actual in itertools.zip_longest(result_rows_v2(group), csv.reader(stream)):
            if expected is None or actual != [value for _, value in expected]:
                raise RuleError("CSVの再読込検証に失敗しました")


def evidence_rows_v2(dataset):
    yield _strings(EVIDENCE_V2_HEADER)
    for index, group in enumerate(dataset["groups"], 1):
        schema = group["schema"]
        for record in group["records"]:
            for field in schema["fields"]:
                state = record["fields"][field["id"]]
                _, precision_reason = _number_and_reason(field, state)
                reason = " / ".join(value for value in (state["reason"], precision_reason) if value)
                anchor = state["anchor"]
                yield _strings([f"結果{index:02d}", schema["id"], schema["version"], *_record_metadata(record),
                    field["id"], field["name"], state["raw"], _field_value(state), state["unit"], STATUS_LABELS.get(state["status"], state["status"]), reason,
                    record["source"]["sha256"], record["source"]["path"], anchor["page"] if anchor else "",
                    *(anchor["rect"] if anchor else ["", "", "", ""]),
                    state["accepted_revision"] if state["accepted_revision"] is not None else "", record["revision"],
                    record.get("assignment_revision", 0)])


def info_rows_v2(dataset, exported_at):
    yield _strings(["区分", "項目・対象", "値・内容", "補足"])
    for label, value in (
        ("確定結果ID", dataset["id"]), ("確定日時 UTC", dataset["created"]), ("出力日時 UTC", exported_at),
        ("対象件数", sum(len(group["records"]) for group in dataset["groups"])),
        ("除外件数", len(dataset["excluded"])),
        ("根拠の参照", "DW-Workbenchで同じ案件の出力履歴を開いてください")):
        yield _strings(["出力", label, value, ""])
    seen_profiles = set()
    for index, group in enumerate(dataset["groups"], 1):
        schema = group["schema"]
        sheet = f"結果{index:02d}"
        yield _strings(["結果表", sheet, schema["name"], str(len(group["records"]))+"件"])
        yield _strings(["項目定義", sheet, schema["id"], schema["version"]])
        for record in group["records"]:
            profile = record["profile"]
            key = (profile["id"], profile["version"])
            if key not in seen_profiles:
                seen_profiles.add(key)
                yield _strings(["テンプレート", profile["name"], profile["id"], "版 "+str(profile["version"])+" / "+sheet])
    for excluded in dataset["excluded"]:
        page = excluded.get("page")
        reason = excluded.get("reason", "")
        unfinished = ", ".join(value for value in excluded.get("fields", ()) if value != reason)
        kind = {"excluded": "対象外", "unassigned": "未選択", "unfinished": "未完了", "incomplete": "未完了", "unregistered": "原本登録未完了"}.get(excluded.get("kind"), excluded.get("kind", ""))
        detail = " / ".join(value for value in (kind, reason, unfinished, "原本ID: "+excluded.get("source_id", "")) if value)
        yield _strings(["除外", excluded.get("name", excluded.get("source_id", "")),
            "ページ "+str(page) if page is not None and page != 0 else "文書", detail])
    for group in dataset["groups"]:
        for record in group["records"]:
            for field in group["schema"]["fields"]:
                _, reason = _number_and_reason(field, record["fields"][field["id"]])
                if reason:
                    yield _strings(["診断", record["id"]+"/"+field["id"], reason, field["name"]])


def _sheet_rows_v2(dataset, exported_at):
    for index, group in enumerate(dataset["groups"], 1):
        yield f"結果{index:02d}", result_rows_v2(group, numeric=True)
    yield "根拠", evidence_rows_v2(dataset)
    yield "出力情報", info_rows_v2(dataset, exported_at)


def write_xlsx_v2(path, dataset, tmpdir):
    """One workbook for the whole frozen project; verification retains only one row."""
    import xlsxwriter
    if not dataset["groups"] or not any(group["records"] for group in dataset["groups"]):
        raise RuleError("出力可能な記録がありません")
    evidence_count = 0
    for group in dataset["groups"]:
        count = len(group["records"])
        fields = len(group["schema"]["fields"])
        if 8+2*fields > 16384 or count > 1048575:
            raise RuleError("Excel結果シートの上限を超えています")
        evidence_count += fields*count
    if evidence_count > 1048575:
        raise RuleError("Excel根拠シートの上限を超えています")
    exported_at = timestamp()
    workbook = xlsxwriter.Workbook(str(path), {"constant_memory": True, "tmpdir": str(tmpdir),
        "strings_to_formulas": False, "strings_to_urls": False, "strings_to_numbers": False})
    try:
        title = workbook.add_format({"bold": True, "bg_color": "#DDEBF7"})
        decimal_format = workbook.add_format({"num_format": "0.##############################"})
        for name, rows in _sheet_rows_v2(dataset, exported_at):
            sheet = workbook.add_worksheet(name)
            last_row = last_col = 0
            for row, values in enumerate(rows):
                for col, (kind, value) in enumerate(values):
                    if kind == "n":
                        status = sheet.write_number(row, col, value, decimal_format)
                    else:
                        status = sheet.write_string(row, col, literal(value), title if row == 0 else None)
                    if status:
                        raise RuleError("Excelセル書込失敗: "+str(status))
                    last_col = max(last_col, col)
                last_row = row
            sheet.freeze_panes(1, 2)
            sheet.set_column(0, min(30, last_col), 20)
            if name.startswith("結果"):
                sheet.autofilter(0, 0, last_row, last_col)
    finally:
        workbook.close()
    verify_xlsx_v2(path, dataset, exported_at)
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


def _unescape_excel(text):
    # One pass prevents a literal _xNNNN_ escape from being decoded twice.
    text = re.sub(r"_x([0-9A-Fa-f]{4})_", lambda match: chr(int(match[1], 16)), text)
    return text.encode("utf-16-le", "surrogatepass").decode("utf-16-le")


def _workbook_sheet_paths(archive):
    """Resolve sheet names through workbook relationships, not numbered ZIP paths."""
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {}
    for relation in relationships:
        if relation.attrib.get("TargetMode") == "External":
            raise RuleError("Excelに外部参照があります")
        target = relation.attrib["Target"]
        targets[relation.attrib["Id"]] = posixpath.normpath(target.lstrip("/") if target.startswith("/") else posixpath.join("xl", target))
    result = []
    for sheet in workbook.find(XML+"sheets"):
        target = targets[sheet.attrib[OFFICE_REL+"id"]]
        if not target.startswith("xl/") or target not in archive.namelist():
            raise RuleError("Excelシートの参照先が不正です")
        result.append((sheet.attrib["name"], target))
    return result


def _read_sheet_rows(archive, path, shared):
    with archive.open(path) as stream:
        parents = []
        for event, element in ET.iterparse(stream, events=("start", "end")):
            if event == "start":
                parents.append(element)
                continue
            if element.tag in (XML+"f", XML+"hyperlink"):
                raise RuleError("Excelに意図しない数式・リンクがあります")
            if element.tag != XML+"row":
                parents.pop()
                continue
            row_index = int(element.attrib["r"])-1
            values = []
            for cell in element.findall(XML+"c"):
                match = re.fullmatch(r"([A-Z]+)(\d+)", cell.attrib["r"])
                if not match or int(match[2])-1 != row_index:
                    raise RuleError("Excelセルの位置が不正です")
                col = 0
                for letter in match[1]:
                    col = col*26+ord(letter)-64
                kind = cell.attrib.get("t", "n")
                if kind == "inlineStr":
                    value = _unescape_excel("".join(node.text or "" for node in cell.findall(".//"+XML+"t")))
                    kind = "s"
                elif kind == "s":
                    value = _unescape_excel(shared[int(cell.findtext(XML+"v"))])
                elif kind == "n":
                    value = float(cell.findtext(XML+"v"))
                else:
                    raise RuleError("Excelセルの型が不正です: "+kind)
                values.append((col-1, kind, value))
            yield row_index, values
            parents[-2].remove(element)
            element.clear()
            parents.pop()


def verify_xlsx_v2(path, dataset, exported_at):
    """Independent row-streaming ZIP/XML validation of all sheets and exact cell types."""
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise RuleError("Excel ZIP CRC失敗: "+bad)
        paths = _workbook_sheet_paths(archive)
        expected_names = [f"結果{index:02d}" for index in range(1, len(dataset["groups"])+1)]+["根拠", "出力情報"]
        if [name for name, _ in paths] != expected_names:
            raise RuleError("Excelシートの構成が不一致です")
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            with archive.open("xl/sharedStrings.xml") as stream:
                for _, element in ET.iterparse(stream, events=("end",)):
                    if element.tag == XML+"si":
                        shared.append("".join(node.text or "" for node in element.findall(".//"+XML+"t")))
                        element.clear()
        for (name, sheet_path), (_, expected_rows) in zip(paths, _sheet_rows_v2(dataset, exported_at)):
            actual_rows = _read_sheet_rows(archive, sheet_path, shared)
            for row, (expected, actual) in enumerate(itertools.zip_longest(expected_rows, actual_rows)):
                values = [(col, kind, value) for col, (kind, value) in enumerate(expected)] if expected is not None else None
                if actual != (row, values):
                    raise RuleError(f"Excel再読込の値・型が不一致: {name} 行{row+1}")


def write_xlsx(path, group, dataset, tmpdir):
    import xlsxwriter
    fields = group["profile"]["fields"]
    header, rows = result_rows(group)
    if len(header) > 16384 or len(rows) > 1048575 or len(fields)*len(rows) > 1048575:
        raise RuleError("Excelシートの上限を超えています")
    expected = {}
    workbook = xlsxwriter.Workbook(str(path), {"constant_memory": True, "tmpdir": str(tmpdir),
        "strings_to_formulas": False, "strings_to_urls": False, "strings_to_numbers": False})
    try:
        sheets = {name: workbook.add_worksheet(name) for name in ("結果", "根拠", "出力情報")}
        title = workbook.add_format({"bold": True, "bg_color": "#DDEBF7"})
        decimal_format = workbook.add_format({"num_format": "0.##############################"})
        def cell(sheet, row, col, value, numeric=False, fmt=None):
            if numeric:
                status = sheets[sheet].write_number(row, col, value, decimal_format)
                expected[(sheet, row, col)] = ("n", value)
            else:
                value = literal(value)
                status = sheets[sheet].write_string(row, col, value, fmt)
                expected[(sheet, row, col)] = ("s", value)
            if status:
                raise RuleError("Excelセル書込失敗: "+str(status))
        for col, name in enumerate(header):
            cell("結果", 0, col, name, fmt=title)
        evidence_header = ["記録ID", "項目ID", "項目名", "原文", "採用値", "単位", "確認状態", "理由・診断", "原本ID", "原本ハッシュ", "原本相対パス", "ページ", "X mm", "Y mm", "幅 mm", "高さ mm", "確認した版", "確定した版"]
        for col, name in enumerate(evidence_header):
            cell("根拠", 0, col, name, fmt=title)
        erow = 1
        diagnostics = []
        for row, record in enumerate(group["records"], 1):
            cell("結果", row, 0, record["source"]["name"])
            cell("結果", row, 1, record["id"])
            for j, f in enumerate(fields):
                state = record["fields"][f["id"]]
                value = state["value"] if state["status"] == Status.ACCEPTED else ""
                number, reason = excel_number(value) if value and f["kind"] == "decimal" else (None, "")
                cell("結果", row, 2+2*j, number if number is not None else value, number is not None)
                cell("結果", row, 3+2*j, state["unit"])
                anchor = state["anchor"]
                evidence = [record["id"], f["id"], f["name"], state["raw"], value, state["unit"], state["status"],
                    state["reason"] or reason, record["source"]["id"], record["source"]["sha256"], record["source"]["path"],
                    anchor["page"] if anchor else "", *(anchor["rect"] if anchor else ["", "", "", ""]),
                    state["accepted_revision"] if state["accepted_revision"] is not None else "", record["revision"]]
                for col, text in enumerate(evidence):
                    cell("根拠", erow, col, str(text))
                erow += 1
                if reason:
                    diagnostics.append(record["id"]+"/"+f["id"]+": "+reason)
        info = [
            ("確定結果ID", dataset["id"]), ("確定日時 UTC", dataset["created"]),
            ("出力日時 UTC", timestamp()),
            ("設定ID", group["profile"]["id"]), ("設定版", str(group["profile"]["version"])),
            ("対象件数", str(len(group["records"]))), ("除外件数（確定結果全体）", str(len(dataset["excluded"]))),
            ("根拠の参照", "DW-Workbenchで同じ案件の出力履歴を開いてください"),
        ] + [("除外", r["name"]+": "+", ".join(r["fields"])) for r in dataset["excluded"]] + [("診断", d) for d in diagnostics]
        for row, pair in enumerate(info):
            for col, text in enumerate(pair):
                cell("出力情報", row, col, text)
        for sheet in sheets.values():
            sheet.freeze_panes(1, 2)
            sheet.set_column(0, min(30, len(header)), 20)
        sheets["結果"].autofilter(0, 0, len(rows), len(header)-1)
    finally:
        workbook.close()
    verify_xlsx(path, expected)
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


def verify_xlsx(path, expected):
    """Independent ZIP/XML reader; validates values, types and absence of formulas."""
    names = ("結果", "根拠", "出力情報")
    actual = {}
    def unescape(text):
        # OOXML escapes literal _xNNNN_ and CR; decode a single pass, including surrogate pairs.
        text = re.sub(r"_x([0-9A-Fa-f]{4})_", lambda m: chr(int(m[1], 16)), text)
        return text.encode("utf-16-le", "surrogatepass").decode("utf-16-le")
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise RuleError("Excel ZIP CRC失敗: "+bad)
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            tree = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.itertext()) for node in tree]
        for i, sheet in enumerate(names, 1):
            tree = ET.fromstring(archive.read(f"xl/worksheets/sheet{i}.xml"))
            if tree.findall(".//"+XML+"f") or tree.findall(".//"+XML+"hyperlink"):
                raise RuleError("Excelに意図しない数式・リンクがあります")
            for c in tree.findall(".//"+XML+"c"):
                match = re.fullmatch(r"([A-Z]+)(\d+)", c.attrib["r"])
                col = 0
                for letter in match[1]:
                    col = col*26+ord(letter)-64
                kind = c.attrib.get("t", "n")
                if kind == "inlineStr":
                    value = unescape("".join(c.find(XML+"is").itertext()))
                    kind = "s"
                elif kind == "s":
                    value = unescape(shared[int(c.findtext(XML+"v"))])
                else:
                    value = float(c.findtext(XML+"v"))
                actual[(sheet, int(match[2])-1, col-1)] = (kind, value)
    if actual != expected:
        differences = [k for k in expected if actual.get(k) != expected[k]]
        raise RuleError("Excel再読込の値・型が不一致: "+str(differences[:5]))


def generate_artifacts(root, dataset, formats, completed=()):
    root = Path(root)
    results = []
    lock = FileLock(root/"staging"/(dataset["id"]+".export.lock"))
    try:
        return _generate(root, dataset, formats, completed)
    finally:
        lock.close()


def _generate(root, dataset, formats, completed):
    if dataset.get("format_version", 1) == 2:
        return _generate_v2(root, dataset, formats, completed)
    results = []
    for format in formats:
        if format not in ("xlsx", "csv"):
            raise RuleError("出力形式が不正です")
        for index, group in enumerate(dataset["groups"], 1):
            name = f"{dataset['id']}-{index}.{format}"
            row = next((r for r in completed if r["dataset_id"] == dataset["id"] and r["name"] == name), None)
            if row and row["status"] == "complete" and (root/row["path"]).is_file() and digest(root/row["path"]) == row["sha256"]:
                results.append(dict(row))
                continue
            stage = root/"staging"/(identifier()+"."+format)
            relative = "exports/"+name
            try:
                if format == "xlsx":
                    write_xlsx(stage, group, dataset, root/"staging")
                else:
                    write_csv(stage, group)
                sha = digest(stage)
                os.replace(stage, root/relative)
                results.append({"name": name, "status": "complete", "path": relative, "sha256": sha})
            except Exception as exc:
                results.append({"name": name, "status": "failed", "error": str(exc)})
            finally:
                stage.unlink(missing_ok=True)
    return results


def _generate_v2(root, dataset, formats, completed):
    if not dataset["groups"] or not any(group["records"] for group in dataset["groups"]):
        raise RuleError("出力可能な記録がありません")
    if any(format not in ("xlsx", "csv") for format in formats):
        raise RuleError("出力形式が不正です")
    results = []
    for format in formats:
        tables = [("案件結果.xlsx", None)] if format == "xlsx" else [
            (f"結果{index:02d}.csv", group) for index, group in enumerate(dataset["groups"], 1)]
        for filename, group in tables:
            name = dataset["id"]+"/"+filename
            relative = "exports/"+name
            stage = root/"staging"/(identifier()+"."+format)
            try:
                row = next((row for row in completed if row["dataset_id"] == dataset["id"] and row["name"] == name), None)
                if row and row["status"] == "complete" and (root/row["path"]).is_file() and digest(root/row["path"]) == row["sha256"]:
                    results.append(dict(row))
                    continue
                if format == "xlsx":
                    write_xlsx_v2(stage, dataset, root/"staging")
                else:
                    write_csv_v2(stage, group)
                sha = digest(stage)
                (root/relative).parent.mkdir(parents=True, exist_ok=True)
                os.replace(stage, root/relative)
                results.append({"name": name, "status": "complete", "path": relative, "sha256": sha})
            except Exception as exc:
                results.append({"name": name, "status": "failed", "error": str(exc)})
            finally:
                stage.unlink(missing_ok=True)
    return results


def record_artifacts(store, dataset, results):
    with store.transaction():
        for row in results:
            relative = row.get("path", "exports/"+row["name"])
            if row["status"] == "complete":
                try:
                    if digest(store.path(relative)) != row["sha256"]:
                        raise RuleError("出力ファイルが生成後に変更されました")
                except (OSError, RuleError) as error:
                    # Publication does not prove that a file is still readable or
                    # unchanged. Reflect a per-file failure in the caller's rows
                    # as well as history so the GUI cannot announce it complete.
                    row["status"] = "failed"
                    row["error"] = "公開した出力ファイルの検証に失敗しました: "+str(error)
                    row.pop("sha256", None)
            store.db.execute("INSERT OR REPLACE INTO artifacts VALUES(?,?,?,?,?,?)", (dataset["id"], row["name"], row["status"],
                relative, row.get("error"), row.get("sha256")))
        store.event("export", dataset["id"])
    # SQL failures intentionally propagate. The caller retains this batch and
    # can retry its history save without regenerating the already-created files.
    return results


def export_dataset(store, dataset, formats):
    results = generate_artifacts(store.root, dataset, formats, store.rows("artifacts"))
    record_artifacts(store, dataset, results)
    return results
