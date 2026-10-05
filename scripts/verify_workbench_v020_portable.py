"""Installed Portable checks at its supplied location, using verification copies.

The caller controls whole-folder relocation. This script never moves the Portable.
All modification, retry and masked-GPU checks use separately backed-up test projects.
"""
import argparse
from dataclasses import asdict
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import subprocess
import sys
import time
import traceback
import zipfile
import psutil

import dw_workbench
from dw_workbench.application import Workbench
from dw_workbench.domain import RuleError, Status, identifier, state_from
from dw_workbench.library import TemplateLibrary
from dw_workbench.storage import FileLock, atomic_bytes, complete_backup, digest, readonly_database
from dw_workbench.workers import WorkerClient, capabilities


def relative_path(root, relative):
    """Independent containment check for persisted references and vendor entries."""
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or Path(relative).drive or Path(relative).root:
        raise AssertionError("Expected a non-empty project-relative path")
    root = Path(root).resolve()
    path = (root/relative).resolve()
    if path == root or not path.is_relative_to(root):
        raise AssertionError("Persisted reference escaped its project")
    return path


def installed_build(portable, vendor):
    if not Path(dw_workbench.__file__).resolve().is_relative_to(portable/"runtime"):
        raise RuntimeError("Run with the supplied Portable runtime/python.exe -I")
    build = json.loads((portable/"BUILD.json").read_text(encoding="utf-8"))
    version = build["version"]
    if dw_workbench.__version__ != version or importlib.metadata.version("dw-workbench") != version:
        raise AssertionError("BUILD/package/metadata versions differ")
    wheel = portable/"wheelhouse"/f"dw_workbench-{version}-py3-none-any.whl"
    if digest(wheel) != build["wheel_sha256"]:
        raise AssertionError("Wheel hash mismatch")
    compared = 0
    with zipfile.ZipFile(wheel) as archive:
        if archive.testzip():
            raise AssertionError("Wheel CRC failure")
        for name in archive.namelist():
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or not name.startswith(("dw_workbench/", f"dw_workbench-{version}.dist-info/")):
                raise AssertionError("Unexpected wheel member")
            if not name.endswith("/"):
                if (portable/"runtime/Lib/site-packages"/name).read_bytes() != archive.read(name):
                    raise AssertionError("Installed wheel member differs: "+name)
                compared += 1
    result = {"build": build, "version_verified": version, "wheel_hash_valid": True, "installed_wheel_members_verified": compared}
    if vendor:
        manifest = json.loads((portable/"licenses/vendor-manifest.json").read_text(encoding="utf-8"))
        for index, item in enumerate(manifest, 1):
            path = relative_path(portable, item["path"])
            if path.stat().st_size != item["bytes"] or digest(path) != item["sha256"]:
                raise AssertionError("Vendor file differs: "+item["path"])
            if index % 2500 == 0:
                print(f"vendor hashes verified {index}/{len(manifest)}", flush=True)
        result["vendor_files_verified"] = len(manifest)
    else:
        result["vendor_files_verified"] = None
        result["vendor_check_skipped"] = True
    return result


def latest_load_project(portable):
    choices = []
    for project in (portable/"projects").iterdir():
        if not project.name.startswith("自動検証 v0.2.0 ") or not (project/"project.sqlite").is_file():
            continue
        database = readonly_database(project/"project.sqlite")
        try:
            if database.execute("PRAGMA user_version").fetchone()[0] != 2:
                continue
            latest = database.execute("SELECT id,data FROM datasets ORDER BY rowid DESC LIMIT 1").fetchone()
            if latest:
                dataset = json.loads(latest[1])
                count = sum(len(group["records"]) for group in dataset["groups"])
                choices.append((count, dataset["created"], project, dataset))
        finally:
            database.close()
    if not choices:
        raise RuntimeError("No completed v0.2.0 synthetic probe/load dataset found")
    _, _, project, dataset = max(choices, key=lambda item: item[:2])
    return project, dataset


def verification_copy(project, destination):
    """Backup a locked source through a read-only connection; do not open/edit it."""
    destination.mkdir(parents=True, exist_ok=False)
    atomic_bytes(destination/"INCOMPLETE.txt", b"Portable verification backup has not completed")
    lock = FileLock(project/".project.lock")
    try:
        before = digest(project/"project.sqlite")
        source = readonly_database(project/"project.sqlite")
        target = sqlite3.connect(destination/"project.sqlite")
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        complete_backup(project, destination)
        # Copy just the first source's first two page images. Other cache is disposable.
        database = readonly_database(destination/"project.sqlite")
        try:
            first = database.execute("SELECT id FROM sources ORDER BY rowid LIMIT 1").fetchone()[0]
        finally:
            database.close()
        folder = project/"cache"/first
        if folder.is_dir():
            for path in folder.glob("page-*"):
                if path.name.startswith(("page-1-", "page-2-")):
                    target = destination/"cache"/first/path.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
        if digest(project/"project.sqlite") != before:
            raise AssertionError("Source DB changed during verification backup")
    finally:
        lock.close()
    return before


def references_relative(app):
    for row in app.store.rows("sources"):
        data = json.loads(row["data"])
        relative_path(app.store.root, data["path"])
    for row in app.store.rows("jobs"):
        data = json.loads(row["data"])
        for name in ("path", "image"):
            if name in data:
                relative_path(app.store.root, data[name])
    for row in app.store.rows("datasets"):
        for group in json.loads(row["data"])["groups"]:
            for record in group["records"]:
                relative_path(app.store.root, record["source"]["path"])
    for row in app.store.rows("artifacts"):
        relative_path(app.store.root, row["path"])
    return True


def child_environment(portable, evidence, masked=False):
    env = os.environ.copy()
    temp = evidence/"child-cache"
    temp.mkdir(parents=True, exist_ok=True)
    env.update({"TEMP": str(temp), "TMP": str(temp), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1",
        "USERPROFILE": str(temp), "PADDLE_PDX_CACHE_HOME": str(temp/"paddlex"), "PADDLE_HOME": str(temp/"paddle"),
        "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "True", "DW_OCR_CACHE": str(temp/"ocr")})
    if masked:
        env["CUDA_VISIBLE_DEVICES"] = "-1"
    return env


def save_child_output(evidence, mode, stdout, stderr):
    """Keep native output byte-exact; only display logs use lossless escapes."""
    (evidence/(mode+"-stdout.bin")).write_bytes(stdout)
    (evidence/(mode+"-stderr.bin")).write_bytes(stderr)
    stdout_display = stdout.decode("utf-8", errors="backslashreplace")
    stderr_display = stderr.decode("utf-8", errors="backslashreplace")
    (evidence/(mode+"-stdout.log")).write_text(stdout_display, encoding="utf-8")
    (evidence/(mode+"-stderr.log")).write_text(stderr_display, encoding="utf-8")
    return stderr_display


def child_result(mode, returncode, stdout, stderr_display):
    if returncode:
        raise RuntimeError(f"{mode} child failed (exit {returncode}): "+stderr_display[-2500:])
    prefix = b"VERIFY_RESULT="
    lines = [line[len(prefix):] for line in stdout.splitlines() if line.startswith(prefix)]
    if len(lines) != 1:
        raise RuntimeError("Child did not report a single verification result: "+mode)
    # Native diagnostics may use CP932. The Python result protocol must be strict UTF-8.
    return json.loads(lines[0].decode("utf-8", errors="strict"))


def run_child(portable, evidence, project, mode):
    command = [str(portable/"runtime/python.exe"), "-I", "-B", "-X", "utf8", str(Path(__file__).resolve()),
        "--portable", str(portable), "--evidence", str(evidence), "--project", str(project), "--child", mode]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=child_environment(portable, evidence, mode == "masked-gpu"), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        stdout, stderr = process.communicate(timeout=120)
    except subprocess.TimeoutExpired:
        # Do not leave this verifier's DocuWorks/OCR subprocesses running on timeout.
        try:
            children = psutil.Process(process.pid).children(recursive=True)
        except psutil.Error:
            children = []
        for child in children:
            try:
                child.kill()
            except psutil.Error:
                pass
        process.kill()
        stdout, stderr = process.communicate(timeout=10)
        save_child_output(evidence, mode, stdout, stderr)
        raise TimeoutError(mode+" child timed out; verifier descendants were stopped")
    stderr_display = save_child_output(evidence, mode, stdout, stderr)
    return child_result(mode, process.returncode, stdout, stderr_display)


def masked_gpu(project, portable):
    import paddle
    count = paddle.device.cuda.device_count()
    if count != 0:
        raise AssertionError("CUDA mask did not hide the GPU from Paddle")
    app = Workbench(project)
    worker = WorkerClient("ocr", portable, project/"logs/masked-gpu-verification.log")
    try:
        record_id = app.store.db.execute("SELECT id FROM records WHERE active=1 ORDER BY rowid LIMIT 1").fetchone()[0]
        row, source, profile = app.context(record_id)
        field = profile.fields[0]
        template = next(item for item in app.store.rows("jobs") if item["kind"] == "ocr" and json.loads(item["data"])["record_id"] == record_id)
        job_id = app.add_job("ocr", json.loads(template["data"]))
        job = app.start_job(job_id)
        failure = None
        try:
            worker.call(app.worker_request(job, portable))
        except RuleError as error:
            failure = str(error)
        if failure is None or "CUDA GPU" not in failure:
            raise AssertionError("Masked GPU did not produce the expected real OCR-unavailable error: "+str(failure))
        app.finish_job(job_id, error=failure)
        row = app.store.record(record_id)
        state = state_from(row["data"]["fields"][field.id])
        value = "PORTABLE手入力検証" if field.kind == "text" else "123.50"
        app.edit(record_id, field.id, row["revision"], value=value, raw="合成検証 手入力", unit=state.unit, anchor=state.anchor)
        if app.store.record(record_id)["data"]["fields"][field.id]["status"] != Status.PENDING:
            raise AssertionError("Manual edit did not require re-confirmation")
        app.accept(record_id, field.id, app.store.record(record_id)["revision"])
        dataset_id = app.finalize()
        artifacts = app.export(dataset_id)
        if any(item["status"] != "complete" for item in artifacts):
            raise AssertionError("Manual export with CUDA masked failed: "+str(artifacts))
        return {"capabilities": capabilities(portable), "actual_cuda_device_count": count,
            "real_ocr_unavailable": True, "ocr_error": failure, "manual_edit_confirm_export": True, "dataset_id": dataset_id}
    finally:
        worker.close()
        app.close()


def gui_smoke(project, portable):
    import tkinter as tk
    from tkinter import messagebox
    from dw_workbench.ui import Window
    root = tk.Tk()
    root.withdraw()
    errors, beats, background_beats = [], [], []
    window = None
    root.report_callback_exception = lambda kind, value, trace: errors.append(str(value))
    messagebox.showerror = lambda title, text, **kwargs: errors.append(title+": "+text)
    def heartbeat():
        beats.append(time.monotonic())
        if window and (window.background or window.active_job):
            background_beats.append(beats[-1])
        root.after(20, heartbeat)
    root.after(20, heartbeat)
    window = Window(root, portable, project)
    def wait(condition, timeout=60):
        until = time.monotonic()+timeout
        while not condition() and time.monotonic() < until:
            root.update()
            time.sleep(.01)
        if not condition():
            raise TimeoutError("Tk source/job operation did not finish")
        root.update()
    try:
        wait(lambda: not window.background)
        source_id = window.app.store.rows("sources")[0]["id"]
        source = window.app.source(source_id)
        window.document_list.selection_set(source_id)
        window.select_source()
        window.tabs.select(window.review_tab)
        window.select_field()
        begin_ticks = len(beats)
        wait(lambda: window.image is not None and not window.background and not window.active_job)
        if window.anchor is None or window.anchor.page != 1:
            raise AssertionError("Page-1 evidence did not select the actual original page")
        window.navigate(1 if len(source.pages) > 1 else 0)
        window.select_field()
        wait(lambda: window.image is not None and not window.background and not window.active_job)
        expected_page = 2 if len(source.pages) > 1 else 1
        if window.page != expected_page or window.anchor.page != expected_page:
            raise AssertionError("Page navigation did not bind the correct evidence")
        latest = window.app.store.rows("datasets")[-1]["id"]
        window.history_list.selection_set(latest)
        window.open_history()
        if len(window.history_records) > 1:
            window.history_record.current(1)
            window.select_history_record()
        window.select_field()
        wait(lambda: window.image is not None and not window.background and not window.active_job)
        if not window.frozen or str(window.entries[0].cget("state")) != "disabled":
            raise AssertionError("Frozen evidence view is not read-only")
        frozen_anchor = asdict(window.anchor)
        window.zoom.set("150%")
        window.show_image()
        window.canvas.xview_moveto(.05)
        window.canvas.yview_moveto(.08)
        if asdict(window.anchor) != frozen_anchor:
            raise AssertionError("Zoom/scroll changed frozen original coordinates")
        window.zoom.set("ページに合わせる")
        window.show_image()
        wait(lambda: len(beats) >= max(3, begin_ticks+2), timeout=5)
        gaps = [second-first for first, second in zip(beats, beats[1:])]
        maximum_gap = max(gaps, default=0)
        if errors or maximum_gap > 1 or not background_beats:
            raise AssertionError("Tk errors/heartbeat gap/background ticks: "+str((errors, maximum_gap, len(background_beats))))
        return {"automated_widget_smoke": True, "actual_source_images_loaded": True, "page_navigation_evidence_verified": True,
            "frozen_evidence_read_only": True, "zoom_scroll_anchor_unchanged": True, "heartbeat_ticks": len(beats),
            "background_heartbeat_ticks": len(background_beats), "maximum_heartbeat_gap_seconds": maximum_gap, "manual_visual_confirmation": False}
    finally:
        wait(lambda: not window.background)
        window.close()


def verify(portable, evidence, vendor=False):
    evidence.mkdir(parents=True, exist_ok=True)
    report = {"portable_root": str(portable), "real_business_document_verified": False, "manual_visual_confirmation": False,
        "whole_folder_move_controlled_by_caller": True, "complete": False, "capabilities": capabilities(portable)}
    app = library = None
    try:
        report.update(installed_build(portable, vendor))
        print("Installed wheel/version/vendor checks complete", flush=True)
        lock = FileLock(portable/"settings/.application.lock")
        try:
            result = subprocess.run([str(portable/"runtime/python.exe"), "-I", "-B", "-X", "utf8", "-m", "dw_workbench"],
                capture_output=True, encoding="utf-8", timeout=20, env=child_environment(portable, evidence),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            report["dual_application_launch_rejected"] = result.returncode != 0 and "別のアプリ" in result.stderr
        finally:
            lock.close()
        if not report["dual_application_launch_rejected"]:
            raise AssertionError("Second application launch was not rejected")
        original, dataset = latest_load_project(portable)
        report["original_project_relative"] = original.relative_to(portable).as_posix()
        report["frozen_records"] = sum(len(group["records"]) for group in dataset["groups"])
        report["frozen_fields"] = sum(len(record["fields"]) for group in dataset["groups"] for record in group["records"])
        token = identifier()[:8]
        copy = portable/"projects"/("Portable検証 コピー "+token)
        original_db_sha = verification_copy(original, copy)
        app = Workbench(copy)
        if not app.store.verify() or app.dataset(dataset["id"]) != dataset:
            raise AssertionError("Relocated source backup/frozen dataset differs")
        report["project_relative_references_verified"] = references_relative(app)
        result = subprocess.run([str(portable/"runtime/python.exe"), "-I", "-B", "-X", "utf8", "-c",
            "import sys;from dw_workbench.application import Workbench;Workbench(sys.argv[1])", str(copy)],
            capture_output=True, encoding="utf-8", timeout=20, env=child_environment(portable, evidence),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        report["dual_project_open_rejected"] = result.returncode != 0 and "別のアプリ" in result.stderr
        if not report["dual_project_open_rejected"]:
            raise AssertionError("Second project open was not rejected")
        completed = [row for row in app.store.rows("artifacts") if row["dataset_id"] == dataset["id"] and row["status"] == "complete"]
        if len(completed) < 2:
            raise AssertionError("Need completed XLSX/CSV artifacts to test isolated retry")
        removed = next(row for row in completed if row["name"].endswith(".csv"))
        retained = {row["path"]: (app.store.path(row["path"]).stat().st_mtime_ns, digest(app.store.path(row["path"]))) for row in completed if row != removed}
        app.store.path(removed["path"]).unlink()
        before = time.perf_counter()
        artifacts = app.export(dataset["id"])
        report["missing_artifact_retry_seconds"] = time.perf_counter()-before
        if any(row["status"] != "complete" for row in artifacts) or any(
            (app.store.path(path).stat().st_mtime_ns, digest(app.store.path(path))) != proof for path, proof in retained.items()):
            raise AssertionError("Retry rewrote completed artifacts or did not regenerate missing CSV")
        report["missing_artifact_only_regenerated"] = True
        profile = app.profiles()[0]
        library = TemplateLibrary(portable)
        app.publish_template(library, profile.id, profile.version)
        library.close()
        library = TemplateLibrary(portable)
        if library.get_profile(profile.id, profile.version) != profile:
            raise AssertionError("Common template version did not reopen")
        import_project = Workbench(portable/"projects"/("Portable検証 共通登録 "+token))
        try:
            import_project.import_template(library, profile.id, profile.version)
            report["common_template_independent_project_import"] = import_project.profile(profile.id, profile.version) == profile and import_project.store.verify()
        finally:
            import_project.close()
        report["library_path_relative"] = library.path.relative_to(portable).as_posix()
        library.close()
        library = None
        app.close()
        app = None
        renamed = copy.with_name("Portable検証 日本語 改名 "+token)
        if copy.parent.resolve() != (portable/"projects").resolve() or renamed.parent.resolve() != copy.parent.resolve():
            raise AssertionError("Verification rename target escaped projects")
        copy.rename(renamed)
        copy = renamed
        app = Workbench(copy)
        report["japanese_space_folder_rename_verified"] = app.store.verify() and app.dataset(dataset["id"]) == dataset
        restored_path = evidence/("独立復元 日本語 "+token)
        app.store.backup(restored_path)
        restored = Workbench(restored_path)
        try:
            report["independent_backup_restore_verified"] = restored.store.verify() and restored.dataset(dataset["id"]) == dataset
            report["restored_assignments"] = len(restored.store.rows("page_assignments"))
        finally:
            restored.close()
        app.close()
        app = None
        report["verification_copy_relative"] = copy.relative_to(portable).as_posix()
        print("Copy, retry, library, rename and restore checks complete; testing CUDA-masked manual workflow", flush=True)
        report["masked_gpu"] = run_child(portable, evidence, copy, "masked-gpu")
        print("CUDA-masked manual workflow complete; testing real Tk page and frozen views", flush=True)
        report["tk"] = run_child(portable, evidence, copy, "tk")
        report["original_project_database_unchanged"] = digest(original/"project.sqlite") == original_db_sha
        if not all(report[key] for key in ("common_template_independent_project_import", "japanese_space_folder_rename_verified",
            "independent_backup_restore_verified", "original_project_database_unchanged")):
            raise AssertionError("Portable copy/restore/original preservation check failed")
        report["complete"] = True
    except BaseException as error:
        report["failure"] = str(error)
        report["traceback"] = traceback.format_exc()
        raise
    finally:
        if app:
            app.close()
        if library:
            library.close()
        (evidence/"verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portable", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--vendor", action="store_true")
    parser.add_argument("--child", choices=("masked-gpu", "tk"), help=argparse.SUPPRESS)
    parser.add_argument("--project", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    portable, evidence = args.portable.resolve(), args.evidence.resolve()
    if args.child:
        if not Path(dw_workbench.__file__).resolve().is_relative_to(portable/"runtime"):
            raise RuntimeError("Child imported an application outside the Portable")
        operation = masked_gpu if args.child == "masked-gpu" else gui_smoke
        print("VERIFY_RESULT="+json.dumps(operation(args.project.resolve(), portable), ensure_ascii=False), flush=True)
    else:
        verify(portable, evidence, args.vendor)
