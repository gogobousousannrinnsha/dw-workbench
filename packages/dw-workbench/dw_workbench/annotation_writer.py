"""Append rectangles only to owned copies, in a separate SDK process."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from .domain import RuleError, identifier, timestamp
from .ledger_marking import COLORS, content_hash, drawing_spec, verify_session, original_ledger_path
from .storage import FileLock, atomic_bytes, digest, readonly_database

ATTRIBUTE = "DW_Workbench_LedgerMarkup_v1"


def check_cancel(cancel):
    if cancel is not None and (cancel.is_set() if isinstance(cancel, threading.Event) else Path(cancel).exists()):
        raise RuleError("注釈出力をキャンセルしました。公開出力は作成していません")


def _snapshot(page):
    from docuworks_ctypes import AnnotationType
    result = []
    for annotation in page.annotations(recursive=True):
        attrs = {}
        names = ["%BorderColor", "%BorderWidth", "%BorderStyle", "%FillColor", "%FillStyle", "%FillTransparent"]
        if annotation.annotation_type == AnnotationType.TEXT:
            names += ["%Text", "%FontSize", "%ForeColor", "%TextOrientation"]
        for name in names:
            try:
                value = annotation.get_standard_attribute(name)
                attrs[name] = value
            except (ValueError, RuntimeError, KeyError, TypeError):
                pass  # Attribute is not available for this annotation type.
        result.append(dict(type=int(annotation.annotation_type), position=asdict(annotation.position),
            size=asdict(annotation.size) if annotation.size is not None else None, attributes=attrs,
            custom=[asdict(a) for a in annotation.custom_attributes()]))
    return result


def native_write(spec, stage, color, plan_id, cancel=None):
    from docuworks_ctypes import XdwApi, OpenMode, RectMM, Color, AnnotationType
    api = XdwApi.load()
    outputs = []
    for entry in spec:
        check_cancel(cancel)
        source = entry["source"]
        original = Path(entry["path"])
        if digest(original) != source["sha256"]:
            raise RuleError("注釈出力前に固定原本が変わりました")
        target = Path(stage)/(source["id"]+"_照合枠.xdw")
        if target.exists() or target.resolve() == original.resolve():
            raise RuleError("出力は新しい原本コピーである必要があります")
        shutil.copyfile(original, target)
        if digest(target) != source["sha256"]:
            raise RuleError("原本コピーのハッシュが一致しません")
        old, identities, geometries, added_by_page = {}, [], [], {}
        with api.open_document(target, mode=OpenMode.UPDATE) as doc:
            if doc.page_count != len(source["pages"]):
                raise RuleError("原本ページ数が確定結果と一致しません")
            for number in range(1, doc.page_count+1):
                page = doc.page(number)
                old[number] = _snapshot(page)
                selected = [m for m in entry["marks"] if m["page"] == number]
                added_by_page[number] = len(selected)
                for mark in selected:
                    check_cancel(cancel)
                    p = source["pages"][number-1]
                    x, y, width, height = mark["rect"]
                    if p["rotation"] != 0 or min(x, y) < 0 or min(width, height) <= 0 or x+width > p["width_mm"]+.001 or y+height > p["height_mm"]+.001:
                        raise RuleError("描画する原本範囲が不正です")
                    # The SDK rectangle minimum is 3mm. Grow only display geometry;
                    # preserve the exact original anchor in the annotation identity.
                    w, h = max(3., width), max(3., height)
                    if w > p["width_mm"] or h > p["height_mm"]:
                        raise RuleError("ページが矩形の最小サイズより小さいです")
                    rx, ry = max(0., min(x+(width-w)/2, p["width_mm"]-w)), max(0., min(y+(height-h)/2, p["height_mm"]-h))
                    identity = dict(schema="dw-workbench-ledger-markup", version=1, plan_id=plan_id,
                        source_id=source["id"], source_sha256=source["sha256"], page=number,
                        anchor_mm=mark["rect"], references=mark["references"])
                    payload = json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
                    annotation = page.add_rectangle(RectMM(rx, ry, w, h), border_color=Color(COLORS[color]),
                        border_width=1, border_visible=True, fill_visible=False)
                    annotation.set_user_attribute(ATTRIBUTE, payload)
                    identities.append(payload)
                    geometries.append((number, rx, ry, w, h))
            doc.save()
        found, rectangles = [], []
        with api.open_document(target) as doc:
            if doc.page_count != len(source["pages"]):
                raise RuleError("保存後のページ数が変わりました")
            for number in range(1, doc.page_count+1):
                page = doc.page(number)
                snapshot = _snapshot(page)
                # Added annotations are top-level leaves; recursive old order remains.
                if len(snapshot) != len(old[number])+added_by_page[number] or snapshot[:len(old[number])] != old[number]:
                    raise RuleError("保存後に既存注釈の構造・内容が変わりました")
                for a in list(page.annotations(recursive=True))[len(old[number]):]:
                    if a.annotation_type != AnnotationType.RECTANGLE or a.get_standard_attribute("%FillStyle") or not a.get_standard_attribute("%BorderStyle"):
                        raise RuleError("保存した注釈が塗りなし矩形ではありません")
                    if a.get_standard_attribute("%BorderColor") != COLORS[color] or a.get_standard_attribute("%BorderWidth") != 1:
                        raise RuleError("保存した矩形の色・線幅が不一致です")
                    found.append(a.get_user_attribute(ATTRIBUTE))
                    rectangles.append((number, a.position.x, a.position.y, a.size.width, a.size.height))
        if found != identities or len(rectangles) != len(geometries) or any(
                any(abs(a-b) > .010001 for a,b in zip(actual, expected)) for actual,expected in zip(rectangles, geometries)):
            raise RuleError("注釈のID・ページ・位置の再読込検証が失敗しました")
        if digest(original) != source["sha256"]:
            raise RuleError("注釈出力中に固定原本が変わりました")
        outputs.append(dict(source_id=source["id"], filename=target.name, sha256=digest(target),
            annotations=len(identities), sdk=api.runtime_info.version_text,
            original_anchor_preserved=True, viewer_status="NOT_CHECKED"))
    check_cancel(cancel)
    return outputs


def sdk_subprocess(spec, stage, color, plan_id, cancel):
    source = str(Path(__file__).parent.parent)
    request = Path(stage)/"sdk-request.json"
    cancel_path = Path(stage)/"CANCEL"
    atomic_bytes(request, json.dumps(dict(spec=spec, stage=str(stage), color=color, plan_id=plan_id,
        cancel=str(cancel_path)), ensure_ascii=False).encode("utf-8"))
    command = [sys.executable, "-I", "-B", "-X", "utf8", "-c",
        "import sys;sys.path.insert(0,sys.argv.pop(1));from dw_workbench.annotation_writer import worker_main;worker_main()", source, str(request)]
    with (Path(stage)/"sdk.log").open("wb") as log:
        process = subprocess.Popen(command, stdout=log, stderr=log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        started = time.monotonic()
        while process.poll() is None:
            if cancel.is_set() and not cancel_path.exists():
                atomic_bytes(cancel_path, b"cancel")
            if time.monotonic()-started > 300:
                process.kill()  # Only this owned SDK child, never an existing app.
                process.wait()
                raise RuleError("注釈用SDK処理が時間内に完了しませんでした")
            time.sleep(.05)
    result = Path(stage)/"sdk-result.json"
    if process.returncode or not result.is_file():
        raise RuleError("SDK注釈出力に失敗しました: "+(Path(stage)/"sdk.log").read_text(encoding="utf-8", errors="replace")[-2000:])
    return json.loads(result.read_text(encoding="utf-8"))


def export_annotations(root, folder, session, *, cancel=None, writer=None, output=None):
    cancel = cancel or threading.Event()
    folder = Path(folder).resolve()
    output = Path(output or folder/("output_"+identifier())).resolve()
    if output.exists() or not output.is_relative_to(folder) or output == folder:
        raise RuleError("注釈出力先は照合保存先内の新しいフォルダーにしてください")
    def verify_live():
        database = readonly_database(Path(root)/"project.sqlite")
        try:
            row = database.execute("SELECT data FROM datasets WHERE id=?", (session["preview"]["dataset_id"],)).fetchone()
            if row is None:
                raise RuleError("確定結果がありません")
            verify_session(folder, session, json.loads(row[0]))
        finally:
            database.close()
        saved = json.loads((folder/"session.json").read_text(encoding="utf-8"))
        if content_hash(saved) != content_hash(session):
            raise RuleError("プレビューの保存内容が変わりました。再読込してください")
    verify_live()
    spec = drawing_spec(root, session)
    lock = FileLock(folder/".output.lock")
    stage = folder/(".stage_"+identifier())
    output_created = False
    published = False
    try:
        stage.mkdir()
        check_cancel(cancel)
        outputs = (writer or sdk_subprocess)(spec, stage, session["preview"]["config"]["color"], session["id"], cancel)
        check_cancel(cancel)
        # Recheck all frozen originals and the original/snapshot ledger at commit.
        verify_live()
        drawing_spec(root, session)
        from .ledger import LedgerBook
        original = original_ledger_path(folder, session)
        expected = session["preview"]["ledger_sha256"]
        if not original.is_file() or digest(original) != expected or LedgerBook(folder/"ledger.xlsx").sha256 != expected:
            raise RuleError("台帳が出力中に変わりました。出力を破棄しました")
        report = dict(plan=deepcopy_session(session), plan_sha256=content_hash(session), created=timestamp(),
                      outputs=outputs, viewer_status="NOT_CHECKED")
        report["completion"] = "complete"
        atomic_bytes(stage/"report.json", json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8"))
        for name in ("sdk-request.json", "sdk-result.json", "CANCEL"):
            (stage/name).unlink(missing_ok=True)
        if output.exists():
            raise RuleError("出力先が既に作成されています")
        check_cancel(cancel)
        # Directory rename is denied on this Windows host under Documents even
        # for a fresh owned empty directory. Use the existing backup protocol:
        # never present a set as completed while INCOMPLETE.txt remains.
        output.mkdir(exist_ok=False)
        output_created = True
        # This folder is newly owned. An exclusive marker write needs no rename.
        with (output/"INCOMPLETE.txt").open("xb") as marker:
            marker.write("出力未完了。このフォルダーを完成成果物として使用しないでください。".encode("utf-8"))
            marker.flush()
            os.fsync(marker.fileno())
        for artifact in outputs:
            name = artifact["filename"]
            if Path(name).name != name or not (stage/name).is_file():
                raise RuleError("注釈出力のファイル名・構成が不正です")
            if digest(stage/name) != artifact["sha256"]:
                raise RuleError("検証後の注釈ファイルが変わりました")
        for file in stage.iterdir():
            if not file.is_file():
                raise RuleError("注釈出力に予期しないフォルダーがあります")
            check_cancel(cancel)
            with file.open("rb") as src, (output/file.name).open("xb") as dest:
                shutil.copyfileobj(src, dest)
                dest.flush()
                os.fsync(dest.fileno())
            if digest(file) != digest(output/file.name):
                raise RuleError("出力先のファイル検証に失敗しました")
        verify_live()
        drawing_spec(root, session)
        check_cancel(cancel)
        (output/"INCOMPLETE.txt").unlink()
        published = True
        return output, report
    finally:
        try:
            if output_created and not published and output.exists():
                if not output.resolve().is_relative_to(folder) or output.resolve() == folder:
                    raise RuleError("出力の後始末先が不正です")
                shutil.rmtree(output)
            if stage.exists():
                if not stage.resolve().is_relative_to(folder) or stage.resolve() == folder:
                    raise RuleError("一時コピーの後始末先が不正です")
                shutil.rmtree(stage)
        finally:
            lock.close()


def deepcopy_session(session):
    return json.loads(json.dumps(session, ensure_ascii=False))


def worker_main():
    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    output = native_write(**request)
    atomic_bytes(Path(request["stage"])/"sdk-result.json", json.dumps(output, ensure_ascii=False).encode("utf-8"))
