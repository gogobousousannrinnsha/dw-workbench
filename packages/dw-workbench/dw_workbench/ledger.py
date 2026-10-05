"""Read one XLSX sheet without Excel, formula evaluation or implicit type conversion."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import io
from pathlib import Path, PurePosixPath
import re
import zipfile
from xml.etree import ElementTree as ET
from .domain import RuleError

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


@dataclass(frozen=True)
class Cell:
    kind: str
    value: str = ""
    formula: str = ""
    style: str = ""

    def display(self):
        if self.kind == "formula":
            return "数式: " + self.formula + "（保存済み結果は不使用）"
        return self.value + (" [" + self.kind + "]" if self.kind not in ("text", "blank") else "")


def _column(reference):
    match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]*)", reference or "")
    if not match:
        raise RuleError("Excelセルの参照が不正です")
    column = 0
    for letter in match[1]:
        column = column * 26 + ord(letter) - 64
    if column > 16384 or int(match[2]) > 1048576:
        raise RuleError("Excelセルが上限を超えています")
    return column, int(match[2])


class LedgerBook:
    def __init__(self, path):
        self.path = Path(path).resolve()
        if self.path.suffix.lower() != ".xlsx":
            raise RuleError("台帳は.xlsxを選択してください（.xls/.xlsmは初版の対象外）")
        self.payload = self.path.read_bytes()
        if len(self.payload) > 32 * 1024 * 1024:
            raise RuleError("初版の台帳上限は32MiBです")
        self.sha256 = hashlib.sha256(self.payload).hexdigest()
        try:
            with zipfile.ZipFile(io.BytesIO(self.payload)) as archive:
                names = archive.namelist()
                if len(names) != len(set(names)) or sum(i.file_size for i in archive.infolist()) > 256 * 1024 * 1024:
                    raise RuleError("ExcelのZIP構成または展開サイズが不正です")
                self._parts = {name: archive.read(name) for name in names if name.startswith("xl/") and name.endswith(".xml")}
                relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
                targets = {}
                for node in relationships:
                    if node.attrib.get("TargetMode") == "External":
                        continue
                    target = node.attrib.get("Target", "")
                    if target.startswith("/"):
                        target = target.lstrip("/")
                    else:
                        target = "xl/" + target
                    if ".." in PurePosixPath(target).parts:
                        raise RuleError("Excelのシート参照が不正です")
                    targets[node.attrib["Id"]] = target
                workbook = ET.fromstring(self._parts["xl/workbook.xml"])
                sheet_nodes = workbook.findall(NS + "sheets/" + NS + "sheet")
                sheet_names = [node.attrib["name"] for node in sheet_nodes]
                if not sheet_names or len(sheet_names) != len(set(sheet_names)):
                    raise RuleError("Excelのシート名が空または重複しています")
                self.sheets = {node.attrib["name"]: targets[node.attrib[REL + "id"]] for node in sheet_nodes}
                self.shared = []
                if "xl/sharedStrings.xml" in self._parts:
                    for item in ET.fromstring(self._parts["xl/sharedStrings.xml"]).findall(NS + "si"):
                        self.shared.append("".join(t.text or "" for t in item.findall(".//" + NS + "t")))
        except (KeyError, ValueError, ET.ParseError, zipfile.BadZipFile) as exc:
            raise RuleError("台帳の.xlsx構成を読み取れません: " + str(exc)) from exc

    def sheet(self, name, header_row):
        if name not in self.sheets or not isinstance(header_row, int) or not 1 <= header_row <= 1048576:
            raise RuleError("シート・見出し行を指定してください")
        try:
            root = ET.fromstring(self._parts[self.sheets[name]])
        except (KeyError, ET.ParseError) as exc:
            raise RuleError("Excelのシート構成を読み取れません") from exc
        rows = {}
        for row in root.findall(NS + "sheetData/" + NS + "row"):
            for node in row.findall(NS + "c"):
                col, number = _column(node.attrib.get("r"))
                cells = rows.setdefault(number, {})
                if col in cells:
                    raise RuleError("Excelに同じセル参照が複数あります")
                value = node.findtext(NS + "v") or ""
                formula = node.find(NS + "f")
                kind = node.attrib.get("t", "n")
                if formula is not None:
                    cell = Cell("formula", value, formula.text or "共有数式", node.attrib.get("s", ""))
                elif kind == "s":
                    try:
                        index = int(value)
                        if not 0 <= index < len(self.shared):
                            raise IndexError(index)
                        cell = Cell("text", self.shared[index])
                    except (ValueError, IndexError) as exc:
                        raise RuleError("Excelの共有文字列参照が不正です") from exc
                elif kind == "inlineStr":
                    cell = Cell("text", "".join(t.text or "" for t in node.findall(".//" + NS + "t")))
                elif kind in ("str", "e", "b", "d"):
                    cell = Cell({"str": "text", "e": "error", "b": "boolean", "d": "date"}[kind], value)
                elif kind == "n":
                    cell = Cell("number" if value else "blank", value, style=node.attrib.get("s", ""))
                else:
                    cell = Cell("unsupported", value)
                cells[col] = cell
        # A merged key is never filled forward from its top-left cell.
        merged = []
        for node in root.findall(NS + "mergeCells/" + NS + "mergeCell"):
            ends = node.attrib.get("ref", "").split(":")
            if len(ends) != 2:
                raise RuleError("結合セル範囲が不正です")
            first, last = _column(ends[0]), _column(ends[1])
            merged.append((*first, *last))
        header = rows.get(header_row, {})
        columns = {col: cell.value for col, cell in header.items() if cell.kind == "text" and cell.value.strip()}
        if not columns:
            raise RuleError("見出し行に文字列の列名がありません")
        data = [(number, cells) for number, cells in sorted(rows.items()) if number > header_row
                and any(cell.kind != "blank" and cell.value != "" or cell.kind == "formula" for cell in cells.values())]
        if len(data) > 100000:
            raise RuleError("初版の台帳上限はデータ10万行です")
        return LedgerSheet(name, header_row, columns, data, merged)


@dataclass
class LedgerSheet:
    name: str
    header_row: int
    columns: dict
    rows: list
    merged: list

    def cell(self, number, cells, column):
        for c1, r1, c2, r2 in self.merged:
            if c1 <= column <= c2 and r1 <= number <= r2:
                return Cell("merged", cells.get(column, Cell("blank")).value)
        return cells.get(column, Cell("blank"))


def exact_value(cell, kind):
    if cell.kind != kind:
        raise RuleError("セル型が不一致: " + cell.kind + "（指定: " + kind + "）")
    if not cell.value.strip():
        raise RuleError("空欄の値です")
    if kind == "text":
        return cell.value  # No trimming, NFKC, zero removal or fuzzy matching.
    if kind != "number":
        raise RuleError("照合型は文字列か数値を指定してください")
    try:
        value = Decimal(cell.value)
    except InvalidOperation as exc:
        raise RuleError("有限の数値が必要です") from exc
    if not value.is_finite() or abs(value.adjusted()) > 1000:
        raise RuleError("有限の数値が必要です")
    return value
