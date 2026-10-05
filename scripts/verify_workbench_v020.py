"""Installed Portable acceptance with real SDK rendering and real GPU OCR.

All generated documents are synthetic test data, NOT BUSINESS DOCUMENTS.
Run with the candidate's runtime/python.exe -I, never with a source-path override.
"""
import argparse
import ctypes
from dataclasses import asdict
from decimal import Decimal
import csv
import json
import math
import os
from pathlib import Path
import shutil
import threading
import time
import traceback
import unicodedata
import zipfile
from xml.etree import ElementTree as ET

import psutil
from PIL import Image, ImageDraw, ImageFont

import dw_workbench
from dw_workbench.application import Workbench
from dw_workbench.domain import ExtractionProfile, FieldSchema, ResultSchema, identifier, state_from
from dw_workbench.storage import digest, validate_sources
from dw_workbench.workers import WorkerClient, capabilities


XML = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def expected_value(page, index):
    return f"{page:03d}{index:03d}" if index % 3 == 1 else f"{page*100+index}.25"


def field_name(index):
    return f"項目{index:03d}"


def layouts(field_count):
    row_count = math.ceil(field_count/3)
    spacing = min(23, 235/max(1, row_count-1))
    result = []
    for layout in (0, 1):
        regions = {}
        for index in range(1, field_count+1):
            col, row = (index-1) % 3, (index-1)//3
            # The two layouts do not overlap: the wrong profile sees blank pixels.
            x, y = 20+65*col+30*layout, 30+row*spacing+3*layout
            regions[f"f{index:03d}"] = {"page": 1, "rect": [x-.7, y-.5, 25, 7.2]}
        result.append(regions)
    return result


def create_fixture(root, page_count, field_count):
    """Two visibly different layouts, with page-specific values in every range."""
    from docuworks_ctypes import XdwApi, OpenMode
    from docuworks_ctypes._raw import types as T, constants as C
    from docuworks_ctypes.encoding import wchar_buffer
    from docuworks_ctypes.errors import check_result

    root.mkdir(parents=True, exist_ok=False)
    font_path = str(Path(os.environ["WINDIR"])/"Fonts/msgothic.ttc")
    value_font = ImageFont.truetype(font_path, 42)
    label_font = ImageFont.truetype(font_path, 22)
    header_font = ImageFont.truetype(font_path, 26)
    api = XdwApi.load()
    regions = layouts(field_count)
    parts = []
    for page in range(1, page_count+1):
        layout = (page-1) % 2
        image = Image.new("RGB", (2100, 2970), "white")
        draw = ImageDraw.Draw(image)
        draw.text((120, 70), f"SYNTHETIC / PAGE {page} / LAYOUT {'AB'[layout]} / NOT BUSINESS", font=header_font, fill="black")
        for index in range(1, field_count+1):
            x, y, _, _ = regions[layout][f"f{index:03d}"]["rect"]
            draw.text((int((x+.7)*10), int((y+.5-5)*10)), f"F{index:03d}", font=label_font, fill="black")
            draw.text((int((x+.7)*10), int((y+.5)*10)), expected_value(page, index), font=value_font, fill="black")
        bmp = root/f"page-{page}.bmp"
        image.save(bmp, dpi=(254, 254))
        part = root/f"page-{page}.xdw"
        options = T.XDW_CREATE_OPTION()
        options.nSize = ctypes.sizeof(options)
        options.nFitImage = C.XDW_CREATE_USERDEF
        options.nWidth, options.nHeight, options.nZoom = 21000, 29700, 100
        for attempt in range(5):
            status = api.raw.XDW_CreateXdwFromImageFileW(wchar_buffer(str(bmp)), wchar_buffer(str(part)), ctypes.byref(options))
            if ctypes.c_uint32(status).value != 0x80070020:
                break
            time.sleep(.2)
        check_result(status, "synthetic fixture creation")
        bmp.unlink()
        parts.append(part)
    document = root/f"合成専用 {page_count}ページ-{field_count}項目.xdw"
    shutil.copyfile(parts[0], document)
    with api.open_document(document, mode=OpenMode.UPDATE) as doc:
        for page, part in enumerate(parts[1:], 2):
            check_result(doc.raw.XDW_InsertDocumentW(doc.handle, page, wchar_buffer(str(part)), None), "synthetic fixture insert")
        doc.save()
    return document


class MemorySampler:
    def __init__(self, clients, peaks):
        self.clients, self.peaks = clients, peaks
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def sample(self):
        self.peaks["application_rss"] = max(self.peaks["application_rss"], psutil.Process().memory_info().rss)
        for name, client in self.clients.items():
            process = client.process
            if process is not None:
                try:
                    if process.poll() is None:
                        key = name+"_worker_rss"
                        self.peaks[key] = max(self.peaks[key], psutil.Process(process.pid).memory_info().rss)
                except (psutil.Error, OSError):
                    pass

    def run(self):
        while not self.stop.wait(.25):
            self.sample()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)
        self.sample()


def inspect_exports(project, dataset, artifacts, field_count):
    """Independent CSV and OOXML streaming read, including every result value."""
    if len(dataset["groups"]) != 1 or any(row["status"] != "complete" for row in artifacts):
        raise AssertionError("Expected one schema table and complete artifacts")
    group = dataset["groups"][0]
    records = group["records"]
    by_record = {record["id"]: record for record in records}
    csv_path = project/next(row["path"] for row in artifacts if row["name"].endswith(".csv"))
    csv_count = 0
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            record = records[csv_count]
            page = record["page"]
            if row["記録ID"] != record["id"] or int(row["元ページ番号"]) != page:
                raise AssertionError("CSV record/page/order mismatch")
            if row["テンプレートID"] != record["profile"]["id"] or row["原本ID"] != record["source"]["id"]:
                raise AssertionError("CSV source/template mismatch")
            for index in range(1, field_count+1):
                if row[field_name(index)] != expected_value(page, index):
                    raise AssertionError(f"CSV value mismatch: {page}/{index}")
                if row[field_name(index)+" 単位"] != ("" if index % 3 == 1 else "℃"):
                    raise AssertionError("CSV unit mismatch")
            csv_count += 1
    if csv_count != len(records):
        raise AssertionError("CSV record count mismatch")
    workbook = project/next(row["path"] for row in artifacts if row["name"].endswith(".xlsx"))
    xml_records = evidence_fields = 0
    with zipfile.ZipFile(workbook) as archive:
        tree = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {row.attrib["Id"]: "xl/"+row.attrib["Target"] for row in relationships}
        sheets = [(sheet.attrib["name"], targets[sheet.attrib[REL+"id"]]) for sheet in tree.find(XML+"sheets")]
        if [name for name, _ in sheets] != ["結果01", "根拠", "出力情報"]:
            raise AssertionError("Different layouts sharing a schema did not produce one result table")
        for name, path in sheets[:2]:
            with archive.open(path) as stream:
                parents = []
                header = None
                for event, element in ET.iterparse(stream, events=("start", "end")):
                    if event == "start":
                        parents.append(element)
                        continue
                    if element.tag == XML+"f" or element.tag == XML+"hyperlink":
                        raise AssertionError("Unexpected formula or hyperlink")
                    if element.tag != XML+"row":
                        parents.pop()
                        continue
                    values = []
                    for cell in element.findall(XML+"c"):
                        if cell.attrib.get("t") == "inlineStr":
                            values.append(("s", "".join(node.text or "" for node in cell.findall(".//"+XML+"t"))))
                        else:
                            values.append(("n", cell.findtext(XML+"v")))
                    if header is None:
                        header = [value for _, value in values]
                    elif name == "結果01":
                        record = records[xml_records]
                        page = record["page"]
                        if values[4] != ("s", record["id"]) or values[3] != ("n", str(page)):
                            raise AssertionError("XLSX record/page mismatch")
                        for index in range(1, field_count+1):
                            actual = values[8+2*(index-1)]
                            expected = expected_value(page, index)
                            if index % 3 == 1:
                                if actual != ("s", expected):
                                    raise AssertionError("XLSX zero-prefixed text lost")
                            elif actual[0] != "n" or Decimal(actual[1]) != Decimal(expected):
                                raise AssertionError("XLSX decimal value/type mismatch")
                        xml_records += 1
                    else:
                        evidence = dict(zip(header, (value for _, value in values)))
                        record = by_record[evidence["記録ID"]]
                        index = int(evidence["項目ID"][1:])
                        page = record["page"]
                        if evidence["採用値"] != expected_value(page, index) or int(evidence["根拠ページ"]) != page:
                            raise AssertionError("Evidence value/original page mismatch")
                        if evidence["テンプレートID"] != record["profile"]["id"] or evidence["確認状態"] != "確認済み":
                            raise AssertionError("Evidence template/state mismatch")
                        evidence_fields += 1
                    parents[-2].remove(element)
                    element.clear()
                    parents.pop()
    if xml_records != len(records) or evidence_fields != len(records)*field_count:
        raise AssertionError("XLSX result/evidence count mismatch")
    return {"csv_records": csv_count, "xlsx_records": xml_records, "xlsx_evidence_fields": evidence_fields,
        "same_schema_layouts_single_table": True}


def run(portable, evidence, count, page_count, field_count):
    if not 1 <= count <= 1000 or not 1 <= page_count <= 1000 or not 1 <= field_count <= 60:
        raise ValueError("documents/pages: 1..1000; fields: 1..60")
    if not Path(dw_workbench.__file__).resolve().is_relative_to(portable/"runtime"):
        raise RuntimeError("Run this script with the installed candidate runtime/python.exe -I")
    evidence.mkdir(parents=True, exist_ok=True)
    project = portable/"projects"/f"自動検証 v0.2.0 {count}文書-{page_count}ページ-{field_count}項目"
    if project.exists():
        raise FileExistsError(project)
    report = {"kind": "synthetic-installed-SDK-GPU-page-load", "real_business_document_verified": False,
        "documents": count, "pages_per_document": page_count, "fields_per_page": field_count,
        "expected_records": count*page_count, "expected_confirmed_fields": count*page_count*field_count,
        "expected_load_ocr_calls": count*page_count*field_count, "load_ocr_calls": 0, "reocr_calls": 0,
        "discarded_worker_results": 0, "blank_roi_calls": 0, "completed_jobs": 0,
        "project_relative": project.relative_to(portable).as_posix(), "ocr_mismatches": [], "complete": False,
        "package_file": str(Path(dw_workbench.__file__).resolve()),
        "build": json.loads((portable/"BUILD.json").read_text(encoding="utf-8")),
        "capabilities": capabilities(portable), "timings": {key: [] for key in ("fixture", "inspect", "render", "ocr", "edit_confirm", "export", "resume", "validation")},
        "peaks": {"application_rss": 0, "docuworks_worker_rss": 0, "ocr_worker_rss": 0},
        "memory_measurement": "Process RSS sampled every 250ms; instantaneous peak and GPU VRAM are not measured"}
    clients = {}
    app = sampler = None
    started = time.perf_counter()
    timings = report["timings"]
    try:
        before = time.perf_counter()
        fixture = create_fixture(evidence/"synthetic-source", page_count, field_count)
        timings["fixture"].append(time.perf_counter()-before)
        report["synthetic_original_sha256"] = digest(fixture)
        app = Workbench(project)
        clients.update({"docuworks": WorkerClient("docuworks", portable, project/"logs/native-v020-verification.log"),
            "ocr": WorkerClient("ocr", portable, project/"logs/ocr-v020-verification.log")})
        sampler = MemorySampler(clients, report["peaks"])
        sampler.thread.start()

        def execute(job_id, counter=None, persist=True):
            job = app.start_job(job_id)
            if job is None:
                return None
            request = app.worker_request(job, portable)
            before = time.perf_counter()
            output = clients["ocr" if job["kind"] == "ocr" else "docuworks"].call(request)
            timings[job["kind"]].append(time.perf_counter()-before)
            if counter:
                report[counter] += 1
            if persist:
                app.finish_job(job_id, output)
                report["completed_jobs"] += 1
            sampler.sample()
            return output

        fields = tuple(FieldSchema(f"f{index:03d}", field_name(index), "text" if index % 3 == 1 else "decimal", True,
            "" if index % 3 == 1 else "℃") for index in range(1, field_count+1))
        schema = ResultSchema(identifier(), 1, "合成専用 共通項目定義", fields)
        app.register_schema(schema)
        profiles = []
        regions = layouts(field_count)
        first_record = first_job = None
        for document in range(1, count+1):
            source_id = app.prepare_source(fixture)
            output = execute("inspect-"+source_id)
            report["docuworks_version"] = output["docuworks"]
            source = app.source(source_id)
            if len(source.pages) != page_count:
                raise AssertionError("SDK page count differs from fixture")
            if not profiles:
                for layout in range(2):
                    profile = ExtractionProfile(identifier(), 1, "合成専用 ページ配置"+"AB"[layout], (source.pages[0],), fields,
                        regions[layout], scope="page", schema_id=schema.id, schema_version=schema.version)
                    app.register_profile(profile)
                    profiles.append(profile)
            app.set_mode(source_id, "page")
            for layout in range(2):
                pages = list(range(1+layout, page_count+1, 2))
                if pages:
                    app.assign_pages(source_id, pages, profiles[layout].id, profiles[layout].version, {page: 0 for page in pages})
            before = time.perf_counter()
            validation = validate_sources(project, [asdict(source)])
            timings["validation"].append(time.perf_counter()-before)
            records = {assignment.page: assignment.current_record_id for assignment in app.assignments(source_id)}
            for page in range(1, page_count+1):
                record_id = records[page]
                jobs = app.ocr_jobs(record_id)
                execute(f"render-{source_id}-{page}-300")
                for index, job_id in enumerate(jobs, 1):
                    output = execute(job_id, "load_ocr_calls")
                    expected = expected_value(page, index)
                    actual = "".join(unicodedata.normalize("NFKC", output["text"]).split())
                    if actual != expected:
                        report["ocr_mismatches"].append({"document": document, "page": page, "field": f"f{index:03d}",
                            "recognized": output["text"], "expected": expected})
                    before = time.perf_counter()
                    candidates = app.candidates(record_id, f"f{index:03d}")
                    if candidates:
                        app.adopt(record_id, candidates[0]["id"], app.store.record(record_id)["revision"])
                    row = app.store.record(record_id)
                    state = state_from(row["data"]["fields"][f"f{index:03d}"])
                    app.edit(record_id, f"f{index:03d}", row["revision"], value=expected, raw=output["text"], unit=state.unit, anchor=state.anchor)
                    app.accept(record_id, f"f{index:03d}", app.store.record(record_id)["revision"], validation=validation)
                    timings["edit_confirm"].append(time.perf_counter()-before)
                if first_record is None:
                    first_record, first_job = record_id, jobs[0]
            report["documents_complete"] = document
            report["records_complete"] = document*page_count
            (evidence/"progress.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
            print(f"document {document}/{count}; pages={report['records_complete']}; real load OCR calls={report['load_ocr_calls']}", flush=True)

        original_record = app.store.record(first_record)
        rerun = app.ocr_jobs(first_record)
        execute(rerun[0], "discarded_worker_results", persist=False)
        # A real worker result exists, but simulate interruption before its DB persistence.
        report["interruption_point"] = "real OCR returned; application closes before committing the worker result"
        for client in clients.values():
            client.close()
        app.close()
        before = time.perf_counter()
        app = Workbench(project)
        timings["resume"].append(time.perf_counter()-before)
        report["interrupted_job_resumed"] = app.job(rerun[0])["status"] == "pending"
        if not report["interrupted_job_resumed"]:
            raise AssertionError("Interrupted running job was not restored to pending")
        for job_id in rerun:
            execute(job_id, "reocr_calls")
        report["reocr_keeps_adopted"] = app.store.record(first_record) == original_record
        if not report["reocr_keeps_adopted"]:
            raise AssertionError("ReOCR changed adopted values or review status")
        request = app.worker_request(app.job(first_job), portable)
        request["data"]["rect"] = [195, 280, 10, 8]
        before = time.perf_counter()
        blank = clients["ocr"].call(request)
        timings["ocr"].append(time.perf_counter()-before)
        report["blank_roi_calls"] += 1
        report["blank_roi_verified"] = blank["text"] == "" and not blank["regions"]
        if not report["blank_roi_verified"]:
            raise AssertionError("Synthetic blank ROI returned text")
        dataset_id = app.finalize()
        dataset = app.dataset(dataset_id)
        if sum(len(group["records"]) for group in dataset["groups"]) != report["expected_records"]:
            raise AssertionError("Frozen record count mismatch")
        report["dataset_id"] = dataset_id
        before = time.perf_counter()
        artifacts = app.export(dataset_id)
        timings["export"].append(time.perf_counter()-before)
        report["artifacts"] = artifacts
        report["independent_export_read"] = inspect_exports(project, dataset, artifacts, field_count)
        report["input_unchanged"] = digest(fixture) == report["synthetic_original_sha256"]
        report["fixed_sources_verified"] = app.store.verify()
        backup = evidence/"backup 案件"
        app.store.backup(backup)
        restored = Workbench(backup)
        try:
            report["backup_verified"] = restored.store.verify() and restored.dataset(dataset_id) == dataset
            report["backup_record_count"] = len(restored.store.rows("records"))
            report["backup_assignments_count"] = len(restored.store.rows("page_assignments"))
        finally:
            restored.close()
        for client in clients.values():
            client.close()
        app.close()
        before = time.perf_counter()
        app = Workbench(project)
        report["reopen_verified"] = app.store.verify() and app.dataset(dataset_id) == dataset
        timings["resume"].append(time.perf_counter()-before)
        report["rendered_pages"] = len([row for row in app.store.rows("jobs") if row["kind"] == "render" and row["status"] == "complete"])
        report["confirmed_fields"] = sum(state["status"] == "accepted" for record in app.store.rows("records")
            for state in app.store.record(record["id"])["data"]["fields"].values())
        report["all_real_ocr_calls"] = report["load_ocr_calls"]+report["reocr_calls"]+report["discarded_worker_results"]+report["blank_roi_calls"]
        if report["load_ocr_calls"] != report["expected_load_ocr_calls"] or report["ocr_mismatches"]:
            raise AssertionError(f"OCR calls/mismatches: {report['load_ocr_calls']} / {len(report['ocr_mismatches'])}")
        if report["confirmed_fields"] != report["expected_confirmed_fields"] or report["rendered_pages"] != report["expected_records"]:
            raise AssertionError("Confirmed field/rendered page count mismatch")
        if not all(report[key] for key in ("input_unchanged", "fixed_sources_verified", "backup_verified", "reopen_verified")):
            raise AssertionError("Input/backup/reopen verification failed")
        report["complete"] = True
    except BaseException as error:
        report["failure"] = str(error)
        report["traceback"] = traceback.format_exc()
        raise
    finally:
        if sampler:
            sampler.close()
        for client in clients.values():
            client.close()
        if app:
            app.close()
        report["elapsed_seconds"] = time.perf_counter()-started
        (evidence/"verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portable", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--documents", type=int, default=100)
    parser.add_argument("--pages", type=int, default=10)
    parser.add_argument("--fields", type=int, default=30)
    arguments = parser.parse_args()
    run(arguments.portable.resolve(), arguments.evidence.resolve(), arguments.documents, arguments.pages, arguments.fields)
