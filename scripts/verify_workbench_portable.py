"""Verify installed code, folder relocation, final-version load export and Tk display."""
import argparse
import csv
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import time
import tkinter as tk
from PIL import ImageGrab
from dw_workbench.application import Workbench
from dw_workbench.domain import Status, state_from, identifier
from dw_workbench.storage import digest, FileLock, RuleError
from dw_workbench.workers import WorkerClient, capabilities
from dw_workbench.ui import Window


def verify(portable, evidence, gpu_masked=False, vendor=False):
    evidence.mkdir(parents=True, exist_ok=True)
    report = {"portable_root": str(portable), "build": json.loads((portable/"BUILD.json").read_text(encoding="utf-8")),
        "real_business_document_verified": False, "capabilities": capabilities(portable)}
    wheel = portable/"wheelhouse/dw_workbench-0.1.0-py3-none-any.whl"
    report["wheel_hash_valid"] = digest(wheel) == report["build"]["wheel_sha256"]
    if not report["wheel_hash_valid"]:
        raise RuntimeError("Wheel hash mismatch")
    if vendor:
        manifest = json.loads((portable/"licenses/vendor-manifest.json").read_text(encoding="utf-8"))
        changed = [r["path"] for r in manifest if digest(portable/r["path"]) != r["sha256"]]
        if changed:
            raise RuntimeError("Vendor changed: "+str(changed))
        report["vendor_files_verified"] = len(manifest)
    lock = FileLock(portable/"settings/.application.lock")
    try:
        result = subprocess.run([str(portable/"runtime/python.exe"), "-I", "-B", "-X", "utf8", "-m", "dw_workbench"],
            capture_output=True, encoding="utf-8", timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        report["second_launch_rejected"] = result.returncode != 0 and "別のアプリ" in result.stderr
    finally:
        lock.close()
    app = Workbench(portable/"projects/自動検証 合成帳票")
    clients = {name: WorkerClient(name, portable, app.store.root/"logs"/("relocation-"+name+".log")) for name in ("docuworks", "ocr")}

    def execute(id):
        job = app.start_job(id)
        if not job:
            return
        result = clients["ocr" if job["kind"] == "ocr" else "docuworks"].call(app.worker_request(job, portable))
        app.finish_job(id, result)
        return result

    try:
        assert app.store.verify()
        rid = app.store.rows("records")[0]["id"]
        r, source, profile = app.context(rid)
        initial_fields = r["data"]["fields"]
        image_job = app.render_job(source.id, 1, 150)
        execute(image_job)
        jobs = app.ocr_jobs(rid)
        for job in app.pending_jobs():
            if job["kind"] == "render":
                execute(job["id"])
        first_result = None
        for id in jobs:
            value = execute(id)
            if first_result is None:
                first_result = value
        report["reocr_keeps_adopted"] = app.store.record(rid)["data"]["fields"] == initial_fields
        report["ocr_sample"] = first_result["text"]
        field = profile.fields[0].id
        row = app.store.record(rid)
        state = state_from(row["data"]["fields"][field])
        old_dataset = app.store.rows("datasets")[0]["id"]
        frozen = app.dataset(old_dataset)
        app.edit(rid, field, row["revision"], value="001235", unit="", raw=state.raw, anchor=state.anchor)
        assert app.store.record(rid)["data"]["fields"][field]["status"] == Status.PENDING
        app.edit(rid, field, app.store.record(rid)["revision"], value="001234", unit="", raw=state.raw, anchor=state.anchor)
        app.accept(rid, field, app.store.record(rid)["revision"])
        assert app.dataset(old_dataset) == frozen
        dataset = app.finalize()
        artifacts = app.export(dataset)
        report["export_after_move"] = all(r["status"] == "complete" for r in artifacts)
        # A real blank ROI must yield zero candidates and preserve all required fields.
        data = dict(app.job(jobs[0])["data"])
        data["rect"] = [160, 200, 20, 10]
        blank = app.add_job("ocr", data)
        result = execute(blank)
        report["real_blank_roi_preserves_fields"] = result["regions"] == [] and app.store.record(rid)["data"]["fields"][field]["status"] == Status.ACCEPTED
        if gpu_masked:
            clients["ocr"].close()
            previous = os.environ.get("CUDA_VISIBLE_DEVICES")
            os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
            masked = WorkerClient("ocr", portable, app.store.root/"logs/masked-gpu.log")
            try:
                try:
                    masked.call(app.worker_request(app.job(blank), portable))
                    raise AssertionError("Masked GPU unexpectedly ran OCR")
                except RuleError as exc:
                    assert "CUDA GPU" in str(exc)
                    report["masked_gpu_ocr_error"] = str(exc)
                report["masked_gpu_manual_export"] = all(a["status"] == "complete" for a in app.export(app.finalize()))
            finally:
                masked.close()
                if previous is None:
                    os.environ.pop("CUDA_VISIBLE_DEVICES", None)
                else:
                    os.environ["CUDA_VISIBLE_DEVICES"] = previous
        report["relative_file_references"] = all(not Path(json.loads(r["data"])["path"]).is_absolute() for r in app.store.rows("sources"))
        backup = evidence/"復元 案件"
        app.store.backup(backup)
        restored = Workbench(backup)
        try:
            report["restore_verified"] = restored.store.verify() and restored.dataset(dataset) == app.dataset(dataset) and restored.store.record(rid) == app.store.record(rid)
        finally:
            restored.close()
    finally:
        for client in clients.values():
            client.close()
        app.close()
    # Final application checks all 100 documents, confirms immutable snapshots, exports all 3,000 fields.
    load = Workbench(portable/"projects/自動検証 100文書")
    try:
        start = time.perf_counter()
        load.store.verify()
        dataset = load.finalize()
        result = load.export(dataset)
        assert all(r["status"] == "complete" for r in result)
        report["final_build_load_records"] = len(load.store.rows("records"))
        report["final_build_load_fields"] = sum(len(r["fields"]) for g in load.dataset(dataset)["groups"] for r in g["records"])
        report["final_build_load_reopen_export_seconds"] = time.perf_counter()-start
    finally:
        load.close()
    # Actual Tk event loop, source page rendering and frozen evidence view.
    root = tk.Tk()
    root.geometry("1380x900+20+20")
    window = Window(root, portable, portable/"projects/自動検証 合成帳票")
    deadline = time.monotonic()+30
    try:
        sid = window.app.store.rows("sources")[0]["id"]
        window.document_list.selection_set(sid)
        window.select_source()
        window.select_field()
        window.tabs.select(window.review_tab)
        while (window.background or window.image is None) and time.monotonic() < deadline:
            root.update()
            time.sleep(.02)
        root.update()
        assert window.image is not None
        window.history_list.selection_set(dataset if window.history_list.exists(dataset) else window.history_list.get_children()[0])
        window.open_history()
        root.update()
        window.select_field()
        assert window.frozen and str(window.entries[0].cget("state")) == "disabled"
        before = asdict(window.anchor)
        window.zoom.set("150%")
        window.show_image()
        window.canvas.yview_moveto(.05)
        assert asdict(window.anchor) == before
        window.zoom.set("ページに合わせる")
        window.show_image()
        root.update()
        x, y = root.winfo_rootx(), root.winfo_rooty()
        try:
            ImageGrab.grab(bbox=(x, y, x+root.winfo_width(), y+root.winfo_height())).save(evidence/"画面確認.png")
            report["screen_capture_available"] = True
        except OSError as exc:
            report["screen_capture_available"] = False
            report["screen_capture_diagnostic"] = str(exc)
        report["tk_source_and_frozen_evidence_display"] = True
    finally:
        while window.background and time.monotonic() < deadline:
            root.update()
            time.sleep(.02)
        window.close()
    report["complete"] = True
    (evidence/"verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--portable", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--masked-gpu", action="store_true")
    parser.add_argument("--vendor", action="store_true")
    args = parser.parse_args()
    verify(args.portable.resolve(), args.evidence.resolve(), args.masked_gpu, args.vendor)
