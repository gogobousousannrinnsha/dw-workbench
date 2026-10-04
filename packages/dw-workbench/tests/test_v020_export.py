"""Frozen schema-table exports, inspected through CSV and OOXML readers."""
from copy import deepcopy
import csv
import json
import sqlite3
import zipfile
from xml.etree import ElementTree as ET

import pytest

from dw_workbench import exporting
from dw_workbench.domain import RuleError


DATE = "2026-10-03T01:02:03+00:00"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


@pytest.fixture
def frozen():
    fields = [
        {"id": "part", "name": "部品番号", "kind": "text", "required": True, "unit": ""},
        {"id": "temperature", "name": "温度", "kind": "decimal", "required": True, "unit": "℃"},
        {"id": "note", "name": "備考", "kind": "text", "required": False, "unit": ""},
    ]
    schema = {"id": "measurements", "version": 1, "name": "測定結果", "fields": fields}
    source = {"id": "source-one", "name": "帳票 日本語.xdw", "sha256": "a"*64, "path": "sources/source-one.xdw"}
    def record(identifier, page, profile_name, precision=False):
        states = {}
        for field, value in zip(fields, ("001234", "1234567890123456.125" if precision else "25.00", "")):
            states[field["id"]] = {
                "value": value, "raw": "１２３４５６７８９０１２３４５６.１２５℃" if precision and field["id"] == "temperature" else value,
                "unit": field["unit"], "status": "not_applicable" if field["id"] == "note" else "accepted",
                "reason": "記載なし" if field["id"] == "note" else "", "accepted_revision": 8 if value else None,
                "anchor": {"source_id": source["id"], "source_hash": source["sha256"], "page": page or 2, "rect": [10, 20, 30, 8]},
            }
        return {"id": identifier, "revision": 9, "source": deepcopy(source), "fields": states, "page": page,
            "profile": {"id": profile_name, "name": profile_name, "version": 2, "fields": deepcopy(fields),
                "scope": "page" if page else "document", "schema_id": schema["id"], "schema_version": schema["version"]},
            "assignment_revision": 4}
    records = [record("record-page1", 1, "測定票A"), record("record-page2", 2, "測定票B", True), record("record-document", None, "文書全体")]
    records[1]["fields"]["part"]["value"] = "=1+1"
    records[1]["fields"]["part"]["raw"] = "=1+1"
    other_schema = deepcopy(schema)
    other_schema["id"] = "different-meaning"
    revised_schema = deepcopy(schema)
    revised_schema["version"] = 2
    return {"id": "frozen-id", "created": DATE, "format_version": 2,
        "groups": [{"schema": schema, "profile": records[0]["profile"], "records": records},
            {"schema": other_schema, "profile": records[0]["profile"], "records": [deepcopy(records[0])]},
            {"schema": revised_schema, "profile": records[0]["profile"], "records": [deepcopy(records[0])]}],
        "excluded": [{"source_id": source["id"], "name": source["name"], "page": 4, "kind": "excluded", "reason": "説明ページ", "fields": []},
            {"source_id": source["id"], "name": source["name"], "page": 5, "kind": "unassigned", "reason": "", "fields": []},
            {"source_id": source["id"], "name": source["name"], "page": 6, "kind": "unfinished", "reason": "", "fields": ["温度"]}]}


def _root(workdir):
    root = workdir/"出力 案件"
    (root/"staging").mkdir(parents=True)
    (root/"exports").mkdir()
    return root


def _xml_rows(path, sheet_path):
    """Test inspection deliberately does not call the production verifier."""
    with zipfile.ZipFile(path) as archive:
        tree = ET.fromstring(archive.read(sheet_path))
        result = []
        for row in tree.findall(".//"+NS+"row"):
            cells = {}
            for cell in row.findall(NS+"c"):
                if cell.attrib.get("t") == "inlineStr":
                    cells[cell.attrib["r"]] = ("s", "".join(cell.find(NS+"is").itertext()))
                else:
                    cells[cell.attrib["r"]] = ("n", float(cell.findtext(NS+"v")))
            result.append(cells)
        return result


def _rewrite_zip(path, mutate):
    with zipfile.ZipFile(path) as source:
        entries = {name: source.read(name) for name in source.namelist()}
    mutate(entries)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as target:
        for name, data in entries.items():
            target.writestr(name, data)


def test_one_project_workbook_schema_tables_and_literal_values(workdir, frozen, monkeypatch):
    monkeypatch.setattr(exporting, "timestamp", lambda: DATE)
    root = _root(workdir)
    artifacts = exporting.generate_artifacts(root, frozen, ("xlsx", "csv"))
    assert [row["name"] for row in artifacts] == ["frozen-id/案件結果.xlsx", "frozen-id/結果01.csv", "frozen-id/結果02.csv", "frozen-id/結果03.csv"]
    assert all(row["status"] == "complete" for row in artifacts)
    workbook = root/artifacts[0]["path"]
    with zipfile.ZipFile(workbook) as archive:
        names = [sheet.attrib["name"] for sheet in ET.fromstring(archive.read("xl/workbook.xml")).find(NS+"sheets")]
        assert names == ["結果01", "結果02", "結果03", "根拠", "出力情報"]
        for name in archive.namelist():
            if name.startswith("xl/worksheets/"):
                xml = ET.fromstring(archive.read(name))
                assert not xml.findall(".//"+NS+"f") and not xml.findall(".//"+NS+"hyperlink")
    rows = _xml_rows(workbook, "xl/worksheets/sheet1.xml")
    assert rows[1]["I2"] == ("s", "001234")
    assert rows[1]["K2"] == ("n", 25.0)
    assert rows[2]["I3"] == ("s", "=1+1")
    assert rows[2]["K3"] == ("s", "1234567890123456.125")
    assert rows[1]["D2"] == ("n", 1)
    assert rows[3]["D4"] == ("s", "") and rows[3]["C4"] == ("s", "文書")
    evidence = _xml_rows(workbook, "xl/worksheets/sheet4.xml")
    assert len(evidence) == 1+5*3
    strings = [value for row in evidence for kind, value in row.values() if kind == "s"]
    assert "１２３４５６７８９０１２３４５６.１２５℃" in strings
    assert "Excelの15桁精度を超えるため文字列" in strings
    info = _xml_rows(workbook, "xl/worksheets/sheet5.xml")
    strings = [value for row in info for kind, value in row.values() if kind == "s"]
    assert "説明ページ" in " / ".join(strings)
    assert "未選択 / 原本ID: source-one" in strings
    assert "未完了 / 温度 / 原本ID: source-one" in strings
    assert "測定票B" in strings and "different-meaning" in strings
    for artifact in artifacts[1:]:
        path = root/artifact["path"]
        assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    with (root/artifacts[1]["path"]).open(encoding="utf-8-sig", newline="") as stream:
        values = list(csv.reader(stream))
    assert values[1][8] == "001234" and values[1][10] == "25.00"
    assert values[2][10] == "1234567890123456.125" and values[3][3] == ""


def test_dynamic_relationship_resolution_and_tamper_detection(workdir, frozen, monkeypatch):
    monkeypatch.setattr(exporting, "timestamp", lambda: DATE)
    root = _root(workdir)
    path = root/"staging"/"direct.xlsx"
    exporting.write_xlsx_v2(path, frozen, root/"staging")
    def rename_sheet(entries):
        entries["xl/worksheets/custom-name.xml"] = entries.pop("xl/worksheets/sheet1.xml")
        name = "xl/_rels/workbook.xml.rels"
        entries[name] = entries[name].replace(b"worksheets/sheet1.xml", b"worksheets/custom-name.xml")
    _rewrite_zip(path, rename_sheet)
    exporting.verify_xlsx_v2(path, frozen, DATE)
    def change_cell(entries):
        name = "xl/worksheets/custom-name.xml"
        entries[name] = entries[name].replace(b"001234", b"001235")
    _rewrite_zip(path, change_cell)
    with pytest.raises(RuleError, match="値・型が不一致"):
        exporting.verify_xlsx_v2(path, frozen, DATE)


@pytest.mark.parametrize("injection", [b"<f>1+1</f>", b'<hyperlinks><hyperlink ref="A1" location="A2"/></hyperlinks>'])
def test_independent_reader_rejects_formula_and_hyperlink(workdir, frozen, monkeypatch, injection):
    monkeypatch.setattr(exporting, "timestamp", lambda: DATE)
    root = _root(workdir)
    path = root/"staging"/"direct.xlsx"
    exporting.write_xlsx_v2(path, frozen, root/"staging")
    def inject(entries):
        name = "xl/worksheets/sheet1.xml"
        if injection.startswith(b"<f>"):
            entries[name] = entries[name].replace(b"<v>25</v>", injection+b"<v>25</v>", 1)
        else:
            entries[name] = entries[name].replace(b"</worksheet>", injection+b"</worksheet>")
    _rewrite_zip(path, inject)
    with pytest.raises(RuleError, match="数式・リンク"):
        exporting.verify_xlsx_v2(path, frozen, DATE)


def test_file_failure_retry_skips_successful_xlsx_and_csv(workdir, frozen, monkeypatch):
    root = _root(workdir)
    original = exporting.write_csv_v2
    def fail_one(path, group):
        if group["schema"]["id"] == "different-meaning":
            raise PermissionError("fixture locked CSV")
        return original(path, group)
    monkeypatch.setattr(exporting, "write_csv_v2", fail_one)
    artifacts = exporting.generate_artifacts(root, frozen, ("xlsx", "csv"))
    assert [row["status"] for row in artifacts] == ["complete", "complete", "failed", "complete"]
    times = {row["path"]: (root/row["path"]).stat().st_mtime_ns for row in artifacts if row["status"] == "complete"}
    completed = [dict(row, dataset_id=frozen["id"]) for row in artifacts]
    monkeypatch.setattr(exporting, "write_csv_v2", original)
    retry = exporting.generate_artifacts(root, frozen, ("xlsx", "csv"), completed)
    assert all(row["status"] == "complete" for row in retry)
    assert all((root/path).stat().st_mtime_ns == modified for path, modified in times.items())
    assert not [path for path in (root/"staging").iterdir() if path.suffix != ".lock"]


def test_overlong_literal_fails_whole_workbook_but_csv_tables_survive(workdir, frozen):
    root = _root(workdir)
    text = "あ"*32768
    frozen["groups"][0]["records"][0]["fields"]["part"]["value"] = text
    artifacts = exporting.generate_artifacts(root, frozen, ("xlsx", "csv"))
    assert artifacts[0]["status"] == "failed"
    assert all(row["status"] == "complete" for row in artifacts[1:])
    assert text in (root/artifacts[1]["path"]).read_text(encoding="utf-8-sig")


def test_csv_preserves_text_above_default_parser_limit(workdir, frozen):
    root = _root(workdir)
    text = "合成テスト"*40000
    frozen["groups"][0]["records"][0]["fields"]["part"]["value"] = text
    artifacts = exporting.generate_artifacts(root, frozen, ("csv",))
    assert all(row["status"] == "complete" for row in artifacts)
    with (root/artifacts[0]["path"]).open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.reader(stream))
    assert rows[1][8] == text


def test_empty_dataset_does_not_generate_files(workdir, frozen):
    root = _root(workdir)
    frozen["groups"] = []
    with pytest.raises(RuleError, match="出力可能"):
        exporting.generate_artifacts(root, frozen, ("xlsx", "csv"))
    assert list((root/"exports").iterdir()) == []


def test_retry_regenerates_corrupt_completed_file_only(workdir, frozen):
    root = _root(workdir)
    artifacts = exporting.generate_artifacts(root, frozen, ("xlsx", "csv"))
    times = {row["path"]: (root/row["path"]).stat().st_mtime_ns for row in artifacts}
    damaged = root/artifacts[2]["path"]
    damaged.write_bytes(b"damaged CSV")
    completed = [dict(row, dataset_id=frozen["id"]) for row in artifacts]
    retry = exporting.generate_artifacts(root, frozen, ("xlsx", "csv"), completed)
    assert all(row["status"] == "complete" for row in retry)
    assert damaged.read_bytes().startswith(b"\xef\xbb\xbf")
    for row in artifacts:
        if root/row["path"] != damaged:
            assert (root/row["path"]).stat().st_mtime_ns == times[row["path"]]


def test_unreadable_completed_workbook_isolated_and_only_failed_file_retried(workdir, frozen, monkeypatch):
    root = _root(workdir)
    initial = exporting.generate_artifacts(root, frozen, ("xlsx",))
    assert initial[0]["status"] == "complete"
    workbook_path = root/initial[0]["path"]
    original_digest = exporting.digest
    def unreadable_workbook(path):
        if path == workbook_path:
            raise PermissionError("fixture: completed workbook cannot be read")
        return original_digest(path)
    monkeypatch.setattr(exporting, "digest", unreadable_workbook)
    artifacts = exporting.generate_artifacts(root, frozen, ("xlsx", "csv"), [dict(initial[0], dataset_id=frozen["id"])])
    assert [row["status"] for row in artifacts] == ["failed", "complete", "complete", "complete"]
    assert "cannot be read" in artifacts[0]["error"]
    csv_proofs = {row["path"]: ((root/row["path"]).stat().st_mtime_ns, original_digest(root/row["path"])) for row in artifacts[1:]}
    monkeypatch.setattr(exporting, "digest", original_digest)
    regenerated = []
    original_writer = exporting.write_xlsx_v2
    def observed_writer(*args):
        regenerated.append(True)
        return original_writer(*args)
    monkeypatch.setattr(exporting, "write_xlsx_v2", observed_writer)
    retry = exporting.generate_artifacts(root, frozen, ("xlsx", "csv"), [dict(row, dataset_id=frozen["id"]) for row in artifacts])
    assert all(row["status"] == "complete" for row in retry)
    assert regenerated == [True]
    assert all(((root/path).stat().st_mtime_ns, original_digest(root/path)) == proof for path, proof in csv_proofs.items())


def _save_frozen(store, frozen):
    store.db.execute("INSERT INTO datasets VALUES(?,?)", (frozen["id"], json.dumps(frozen, ensure_ascii=False)))


def test_export_dataset_reports_post_publication_read_failure_and_retains_other_files(app, frozen, monkeypatch):
    _save_frozen(app.store, frozen)
    workbook_path = app.store.root/"exports/frozen-id/案件結果.xlsx"
    original_digest = exporting.digest
    def denied_after_publish(path):
        if path == workbook_path:
            raise PermissionError("fixture: published workbook temporarily unreadable")
        return original_digest(path)
    monkeypatch.setattr(exporting, "digest", denied_after_publish)
    artifacts = app.export(frozen["id"])
    assert [row["status"] for row in artifacts] == ["failed", "complete", "complete", "complete"]
    assert "公開した" in artifacts[0]["error"] and "temporarily unreadable" in artifacts[0]["error"]
    assert "sha256" not in artifacts[0]
    saved = {row["name"]: row for row in app.store.rows("artifacts")}
    assert saved[artifacts[0]["name"]]["status"] == "failed" and saved[artifacts[0]["name"]]["sha256"] is None
    assert all(saved[row["name"]]["status"] == "complete" for row in artifacts[1:])
    times = {row["path"]: (app.store.root/row["path"]).stat().st_mtime_ns for row in artifacts[1:]}
    monkeypatch.setattr(exporting, "digest", original_digest)
    assert all(row["status"] == "complete" for row in app.export(frozen["id"]))
    assert all((app.store.root/path).stat().st_mtime_ns == modified for path, modified in times.items())
    assert app.dataset(frozen["id"]) == frozen


def test_post_publication_hash_mismatch_updates_results_and_preserves_valid_csv_history(app, frozen):
    _save_frozen(app.store, frozen)
    artifacts = exporting.generate_artifacts(app.store.root, frozen, ("xlsx", "csv"))
    app.store.path(artifacts[0]["path"]).write_bytes(b"fixture changed after publication")
    assert exporting.record_artifacts(app.store, frozen, artifacts) is artifacts
    assert artifacts[0]["status"] == "failed" and "変更されました" in artifacts[0]["error"]
    assert all(row["status"] == "complete" for row in artifacts[1:])
    saved = {row["name"]: row for row in app.store.rows("artifacts")}
    assert saved[artifacts[0]["name"]]["status"] == "failed" and saved[artifacts[0]["name"]]["sha256"] is None
    assert all(saved[row["name"]]["sha256"] == row["sha256"] for row in artifacts[1:])


def test_sql_history_failure_propagates_and_batch_can_be_saved_without_regeneration(app, frozen, monkeypatch):
    _save_frozen(app.store, frozen)
    artifacts = exporting.generate_artifacts(app.store.root, frozen, ("xlsx", "csv"))
    file_proofs = {row["path"]: ((app.store.root/row["path"]).stat().st_mtime_ns, row["sha256"]) for row in artifacts}
    app.store.db.execute("PRAGMA query_only=ON")
    with pytest.raises(sqlite3.OperationalError):
        exporting.record_artifacts(app.store, frozen, artifacts)
    assert app.store.rows("artifacts") == []
    assert all(row["status"] == "complete" for row in artifacts)
    app.store.db.execute("PRAGMA query_only=OFF")
    monkeypatch.setattr(exporting, "generate_artifacts", lambda *a, **k: pytest.fail("History retry must not regenerate files"))
    exporting.record_artifacts(app.store, frozen, artifacts)
    assert len(app.store.rows("artifacts")) == 4
    assert all(((app.store.root/path).stat().st_mtime_ns, exporting.digest(app.store.root/path)) == proof for path, proof in file_proofs.items())


def test_legacy_dataset_keeps_original_artifacts_and_verifier(workdir, frozen):
    root = _root(workdir)
    legacy = {key: value for key, value in deepcopy(frozen).items() if key != "format_version"}
    legacy["groups"] = legacy["groups"][:1]
    artifacts = exporting.generate_artifacts(root, legacy, ("xlsx", "csv"))
    assert [row["name"] for row in artifacts] == ["frozen-id-1.xlsx", "frozen-id-1.csv"]
    assert all(row["status"] == "complete" for row in artifacts)
    with zipfile.ZipFile(root/artifacts[0]["path"]) as archive:
        assert [sheet.attrib["name"] for sheet in ET.fromstring(archive.read("xl/workbook.xml")).find(NS+"sheets")] == ["結果", "根拠", "出力情報"]


def test_escaped_text_and_precision_boundaries_remain_literal(workdir, frozen, monkeypatch):
    monkeypatch.setattr(exporting, "timestamp", lambda: DATE)
    root = _root(workdir)
    values = ["_x0041_\r改行\n😀", "https://example.invalid/", "+1-2", "@SUM(A1)"]
    record = frozen["groups"][0]["records"][0]
    for index, value in enumerate(values):
        copy = deepcopy(record)
        copy["id"] = "escaped-"+str(index)
        copy["fields"]["part"]["value"] = value
        copy["fields"]["part"]["raw"] = value
        frozen["groups"][0]["records"].append(copy)
    exporting.write_xlsx_v2(root/"staging"/"direct.xlsx", frozen, root/"staging")
    exporting.verify_xlsx_v2(root/"staging"/"direct.xlsx", frozen, DATE)
