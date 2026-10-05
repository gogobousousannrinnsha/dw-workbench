"""Real SDK/GPU and target-load acceptance using clearly labelled synthetic documents."""
import argparse
import ctypes
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import unicodedata
import psutil
from PIL import Image, ImageDraw, ImageFont
from dw_workbench.application import Workbench
from dw_workbench.domain import ExtractionProfile, FieldSchema, PageInfo, Anchor, identifier, state_from
from dw_workbench.storage import digest
from dw_workbench.workers import WorkerClient


def create_fixture(root):
    from docuworks_ctypes import XdwApi, OpenMode
    from docuworks_ctypes._raw import types as T, constants as C
    from docuworks_ctypes.encoding import wchar_buffer
    from docuworks_ctypes.errors import check_result
    root.mkdir(parents=True, exist_ok=True)
    api = XdwApi.load()
    parts = []
    font = ImageFont.truetype(str(Path(os.environ["WINDIR"])/"Fonts/msgothic.ttc"), 52)
    for page in range(1, 11):
        existing = root/f"page-{page}.xdw"
        if existing.exists():
            parts.append(existing)
            continue
        image = Image.new("RGB", (2100, 2970), "white")
        draw = ImageDraw.Draw(image)
        draw.text((120, 100), f"SYNTHETIC TEST / PAGE {page} / NOT A BUSINESS DOCUMENT", font=font, fill="black")
        for y, text in ((400, "部品番号：001234"), (800, "設定温度：25.0℃"), (1200, "測定温度：23.0℃")):
            draw.text((180, y), text, font=font, fill="black")
        bmp = root/f"page-{page}.bmp"
        image.save(bmp, dpi=(254, 254))
        part = root/f"page-{page}.xdw"
        option = T.XDW_CREATE_OPTION()
        option.nSize = ctypes.sizeof(option)
        option.nFitImage = C.XDW_CREATE_USERDEF
        option.nWidth, option.nHeight, option.nZoom = 21000, 29700, 100
        for attempt in range(5):
            status = api.raw.XDW_CreateXdwFromImageFileW(wchar_buffer(str(bmp)), wchar_buffer(str(part)), ctypes.byref(option))
            if ctypes.c_uint32(status).value != 0x80070020:
                break
            time.sleep(.2)
        check_result(status, "synthetic fixture")
        bmp.unlink()
        parts.append(part)
    document = root/"合成帳票 10ページ.xdw"
    if document.exists():
        return document
    shutil.copyfile(parts[0], document)
    with api.open_document(document, mode=OpenMode.UPDATE) as doc:
        for page, part in enumerate(parts[1:], 2):
            check_result(doc.raw.XDW_InsertDocumentW(doc.handle, page, wchar_buffer(str(part)), None), "synthetic insert")
        doc.save()
    return document


def run(portable, evidence, count):
    evidence.mkdir(parents=True, exist_ok=True)
    fixture = create_fixture(evidence/"synthetic-source")
    input_sha = digest(fixture)
    project = portable/"projects"/("自動検証 100文書" if count == 100 else "自動検証 合成帳票")
    if project.exists():
        raise FileExistsError(project)
    app = Workbench(project)
    clients = {"docuworks": WorkerClient("docuworks", portable, project/"logs/native-verification.log"),
        "ocr": WorkerClient("ocr", portable, project/"logs/ocr-verification.log")}
    timings = {"inspect": [], "render": [], "ocr": [], "edit_confirm": [], "export": [], "resume": []}
    peaks = {"application_rss": 0, "docuworks_worker_rss": 0, "ocr_worker_rss": 0}
    report = {"kind": "synthetic-end-to-end", "documents": count, "pages_per_document": 10, "fields_per_document": 30,
        "real_business_document_verified": False, "project_relative": project.relative_to(portable).as_posix(), "timings": timings,
        "peaks": peaks, "ocr_mismatches": [], "completed_jobs": 0}
    report["build"] = json.loads((portable/"BUILD.json").read_text(encoding="utf-8"))

    def memory():
        peaks["application_rss"] = max(peaks["application_rss"], psutil.Process().memory_info().rss)
        for name, client in clients.items():
            if client.process and client.process.poll() is None:
                key = name+"_worker_rss"
                peaks[key] = max(peaks[key], psutil.Process(client.process.pid).memory_info().rss)

    def execute(id):
        job = app.start_job(id)
        if not job:
            return
        request = app.worker_request(job, portable)
        begin = time.perf_counter()
        result = clients["ocr" if job["kind"] == "ocr" else "docuworks"].call(request)
        duration = time.perf_counter()-begin
        app.finish_job(id, result)
        timings[job["kind"]].append(duration)
        report["completed_jobs"] += 1
        memory()
        return result

    try:
        profile = None
        for n in range(count):
            sid = app.prepare_source(fixture)
            result = execute("inspect-"+sid)
            report["docuworks_version"] = result["docuworks"]
            source = app.source(sid)
            if profile is None:
                fields, regions = [], {}
                for page in range(1, 11):
                    for k, y in (("part", 40), ("set", 80), ("actual", 120)):
                        id = f"p{page}-{k}"
                        fields.append(FieldSchema(id, f"{page}ページ {k}", "text" if k == "part" else "decimal", True, "" if k == "part" else "℃"))
                        # Values start after five Japanese glyphs, around x44 mm.
                        regions[id] = {"page": page, "rect": [44, y-1, 30, 9]}
                profile = ExtractionProfile(identifier(), 1, "合成10ページ・30項目", source.pages, tuple(fields), regions)
                app.register_profile(profile)
            rid = app.apply_profile(sid, profile.id, profile.version)
            jobs = app.ocr_jobs(rid)
            renders = [r["id"] for r in app.pending_jobs() if r["kind"] == "render"]
            for id in renders:
                execute(id)
            for id in jobs:
                output = execute(id)
                expected = "001234" if id == jobs[0] else None
                field = app.job(id)["data"]["field_id"]
                expected = "001234" if field.endswith("part") else "25.0" if field.endswith("set") else "23.0"
                text = unicodedata.normalize("NFKC", output["text"]).replace(" ", "").replace("℃", "").replace("°C", "")
                if text != expected:
                    report["ocr_mismatches"].append({"document": n+1, "field": field, "recognized": output["text"], "expected": expected})
                before = time.perf_counter()
                candidates = app.candidates(rid, field)
                if candidates:
                    app.adopt(rid, candidates[0]["id"], app.store.record(rid)["revision"])
                r = app.store.record(rid)
                state = state_from(r["data"]["fields"][field])
                app.edit(rid, field, r["revision"], value=expected, unit=state.unit, raw=output["text"], anchor=state.anchor)
                app.accept(rid, field, app.store.record(rid)["revision"])
                timings["edit_confirm"].append(time.perf_counter()-before)
            # Progress remains readable while the full load is running.
            report["documents_complete"] = n+1
            (evidence/"progress.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
            print(f"document {n+1}/{count} complete; jobs={report['completed_jobs']}", flush=True)
        record = app.store.rows("records")[0]
        before = app.store.record(record["id"])
        rerun = app.ocr_jobs(record["id"])
        execute(rerun[0])
        report["reocr_keeps_adopted"] = app.store.record(record["id"]) == before
        # Complete the remaining re-OCR tasks so move/resume doesn't require a hidden unfinished run.
        for id in rerun[1:]:
            execute(id)
        dataset_id = app.finalize()
        report["dataset_id"] = dataset_id
        start = time.perf_counter()
        artifacts = app.export(dataset_id)
        timings["export"].append(time.perf_counter()-start)
        if any(a["status"] != "complete" for a in artifacts):
            raise RuntimeError(str(artifacts))
        report["artifacts"] = artifacts
        report["input_unchanged"] = digest(fixture) == input_sha
        backup = evidence/"backup 案件"
        app.store.backup(backup)
        restored = Workbench(backup)
        try:
            report["backup_verified"] = restored.store.verify() and restored.dataset(dataset_id) == app.dataset(dataset_id)
            report["backup_record_count"] = len(restored.store.rows("records"))
        finally:
            restored.close()
        for client in clients.values():
            client.close()
        memory()
        app.close()
        start = time.perf_counter()
        app = Workbench(project)
        report["reopen_verified"] = app.store.verify()
        timings["resume"].append(time.perf_counter()-start)
        report["complete"] = True
    finally:
        for client in clients.values():
            client.close()
        app.close()
        (evidence/"verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--portable", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--documents", type=int, default=100)
    args = parser.parse_args()
    run(args.portable.resolve(), args.evidence.resolve(), args.documents)
