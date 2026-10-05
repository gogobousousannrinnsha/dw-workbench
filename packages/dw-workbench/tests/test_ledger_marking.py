"""Typed XLSX input, frozen decisions and guarded annotation output failures."""
from copy import deepcopy
import json
from pathlib import Path
import threading
import shutil
import pytest
import xlsxwriter
from conftest import complete
from dw_workbench.domain import RuleError
from dw_workbench.ledger import LedgerBook, Cell, exact_value
from dw_workbench.ledger_marking import (build_preview, save_session, load_session, save_decisions,
    verify_session, drawing_spec, summary, original_ledger_path)
from dw_workbench.annotation_writer import export_annotations
from dw_workbench.storage import digest


def book(path, rows, *, merged=False):
    with xlsxwriter.Workbook(str(path), {"strings_to_formulas":False,"strings_to_numbers":False}) as wb:
        ws = wb.add_worksheet("台帳")
        ws.write_row(0,0,["部品番号","判定","備考"])
        for r,row in enumerate(rows,1):
            for c,value in enumerate(row):
                if isinstance(value,tuple):
                    if value[0]=="formula":
                        ws.write_formula(r,c,value[1],None,value[2])
                    elif value[0]=="number":
                        ws.write_number(r,c,value[1],wb.add_format({"num_format":"000000"}))
                elif value is not None:
                    ws.write_string(r,c,value)
        if merged:
            ws.merge_range("A2:A3","001234")
    return LedgerBook(path)


@pytest.fixture
def frozen(app,sample):
    complete(app,sample[2])
    dataset=app.dataset(app.finalize())
    schema=dataset["groups"][0]["schema"]
    cfg=dict(schema_id=schema["id"],schema_version=schema["version"],key_field="part",draw_field="temp",
             sheet="台帳",header_row=1,key_column=1,condition_column=2,key_kind="text",
             condition_kind="text",condition_value="要マーク",color="red")
    return dataset,cfg


def test_exact_text_keys_condition_and_distinct_draw_field(app,workdir,frozen):
    dataset,cfg=frozen
    ledger=book(workdir/"合成 台帳.xlsx",[["001234","要マーク"]])
    before=ledger.path.read_bytes()
    folder,session=save_session(app.store.root,dataset,ledger,cfg)
    assert summary(session)["record"]=={"target":1}
    target=session["preview"]["records"][0]
    assert target["extracted_key"]=="001234" and target["extracted_value"]=="25.0"
    assert target["anchor"]["rect"]==[10,40,30,8]
    assert target["draw_field_id"]=="temp" and target["key_field_id"]=="part"
    assert load_session(folder,dataset)==session
    assert drawing_spec(app.store.root,session)[0]["marks"][0]["references"][0]["field_id"]=="temp"
    assert ledger.path.read_bytes()==before


@pytest.mark.parametrize("rows,reason",[
    ([[ ("number",1234),"要マーク"]],"完全一致"),
    ([["001234","要マーク"],["001234","不要"]],"重複"),
    ([["1234","要マーク"]],"完全一致"),
    ([[" 001234","要マーク"]],"完全一致"),
    ([[None,"要マーク"]],"完全一致"),
    ([["001234",("formula",'="要マーク"',"要マーク")]],"セル型"),
    ([["001234",None]],"セル型"),
    ([[ ("formula",'="001234"',"001234"),"要マーク"]],"完全一致"),
])
def test_ambiguous_unsupported_or_missing_never_marks(app,workdir,frozen,rows,reason):
    dataset,cfg=frozen
    folder,session=save_session(app.store.root,dataset,book(workdir/"ledger.xlsx",rows),cfg)
    assert session["preview"]["records"][0]["status"]=="review"
    assert reason in session["preview"]["records"][0]["reason"]
    with pytest.raises(RuleError,match="要確認"):
        drawing_spec(app.store.root,session)


def test_merged_key_duplicate_extracted_keys_and_false_condition(workdir,frozen):
    dataset,cfg=frozen
    merged=build_preview(dataset,book(workdir/"merged.xlsx",[["001234","要マーク"],[None,"不要"]],merged=True),cfg)
    assert merged["records"][0]["status"]=="review"
    assert all(n["ledger_key"]["kind"]=="merged" for n in merged["notices"])
    ledger=book(workdir/"normal.xlsx",[["001234","不要"]])
    assert build_preview(dataset,ledger,cfg)["records"][0]["status"]=="non_target"
    duplicate=deepcopy(dataset)
    second=deepcopy(duplicate["groups"][0]["records"][0])
    second["id"]="another-record"
    duplicate["groups"][0]["records"].append(second)
    assert all(r["status"]=="review" for r in build_preview(duplicate,ledger,cfg)["records"])


def test_numeric_comparison_is_explicit_and_never_text_coercion(workdir,frozen):
    dataset,cfg=frozen
    cfg=dict(cfg,key_field="temp",key_kind="number",condition_kind="number",condition_value="1")
    ledger=book(workdir/"numbers.xlsx",[[ ("number",25), ("number",1)]])
    assert build_preview(dataset,ledger,cfg)["records"][0]["status"]=="target"
    with pytest.raises(RuleError):
        exact_value(Cell("number","1234"),"text")
    assert exact_value(Cell("text","001234"),"text")=="001234"


def test_exclusion_reasons_persist_and_can_be_undone(app,workdir,frozen):
    dataset,cfg=frozen
    folder,session=save_session(app.store.root,dataset,book(workdir/"ledger.xlsx",[["001234","要マーク"],["OTHER","要マーク"]]),cfg)
    assert summary(session)["ledger"]=={"review":1}
    session["exclusions"]["ledger:3"]="今回の案件の対象外"
    save_decisions(folder,session)
    loaded=load_session(folder,dataset)
    assert summary(loaded)["ledger"]=={"excluded":1} and drawing_spec(app.store.root,loaded)
    loaded["exclusions"].clear()
    with pytest.raises(RuleError,match="要確認"):
        drawing_spec(app.store.root,loaded)
    session["exclusions"]["ledger:3"]=" "
    with pytest.raises(RuleError,match="理由"):
        save_decisions(folder,session)


def test_changed_ledger_dataset_snapshot_and_instructions_are_rejected(app,workdir,frozen):
    dataset,cfg=frozen
    ledger=book(workdir/"ledger.xlsx",[["001234","要マーク"]])
    folder,session=save_session(app.store.root,dataset,ledger,cfg)
    changed=deepcopy(dataset)
    changed["groups"][0]["records"][0]["fields"]["temp"]["value"]="99"
    with pytest.raises(RuleError,match="確定結果"):
        verify_session(folder,session,changed)
    session["preview"]["records"][0]["anchor"]["rect"][0]=999
    with pytest.raises(RuleError,match="マーク指示"):
        verify_session(folder,session,dataset)
    session["preview"]["records"][0]["anchor"]["rect"][0]=10
    ledger.path.write_bytes(b"changed")
    with pytest.raises(RuleError,match="元台帳"):
        verify_session(folder,session,dataset)


@pytest.mark.parametrize("scope", ["project", "portable"])
def test_local_ledger_reference_moves_and_still_rejects_changed_original(workdir, frozen, scope):
    dataset,cfg=frozen
    portable=workdir/"Portable 日本語 空白"
    project=portable/"projects/案件"
    ledger_path=(project if scope=="project" else portable)/"INPUT/台帳.xlsx"
    ledger_path.parent.mkdir(parents=True)
    ledger=book(ledger_path,[["001234","要マーク"]])
    folder,session=save_session(project,dataset,ledger,cfg)
    assert session["ledger_reference"]["scope"]==scope
    relative=folder.relative_to(portable)
    moved=workdir/"移動先 日本語 空白"
    portable.rename(moved)
    saved=load_session(moved/relative,dataset)
    current=original_ledger_path(moved/relative,saved)
    assert current.is_relative_to(moved) and digest(current)==saved["preview"]["ledger_sha256"]
    current.write_bytes(b"changed original after move")
    with pytest.raises(RuleError,match="元台帳"):
        verify_session(moved/relative,saved,dataset)


@pytest.mark.parametrize("path", ["../outside.xlsx", "/outside.xlsx", "C:outside.xlsx"])
def test_saved_relative_ledger_reference_rejects_escape(app,workdir,frozen,path):
    dataset,cfg=frozen
    ledger=book(workdir/"ledger.xlsx",[["001234","要マーク"]])
    folder,session=save_session(app.store.root,dataset,ledger,cfg)
    session["ledger_reference"]={"scope":"project","path":path}
    with pytest.raises(RuleError):
        original_ledger_path(folder,session)


def fake_writer(spec,stage,color,plan_id,cancel):
    outputs=[]
    for entry in spec:
        target=stage/(entry["source"]["id"]+".xdw")
        target.write_bytes(b"synthetic non-SDK output")
        outputs.append(dict(filename=target.name,annotations=len(entry["marks"]),sha256=digest(target)))
    return outputs


@pytest.mark.parametrize("scope", ["project", "portable"])
def test_saved_session_can_export_again_after_whole_portable_move(app,workdir,frozen,scope):
    from dw_workbench.application import Workbench
    dataset,cfg=frozen
    portable=workdir/"Portable relocation"
    project=portable/"projects/case"
    app.close()
    shutil.copytree(app.store.root,project)
    ledger_path=(project if scope=="project" else portable)/"INPUT/ledger.xlsx"
    ledger_path.parent.mkdir(parents=True)
    folder,session=save_session(project,dataset,book(ledger_path,[["001234",cfg["condition_value"]]]),cfg)
    relative=folder.relative_to(portable)
    moved=workdir/"Moved Portable"
    portable.rename(moved)
    current_project=moved/"projects/case"
    current_folder=moved/relative
    reopened=Workbench(current_project)
    try:
        saved=load_session(current_folder,reopened.dataset(dataset["id"]))
        output,report=export_annotations(current_project,current_folder,saved,writer=fake_writer)
        assert report["completion"]=="complete" and len(report["outputs"])==1
        assert not (output/"INCOMPLETE.txt").exists()
        original_ledger_path(current_folder,saved).write_bytes(b"changed ledger")
        with pytest.raises(RuleError):
            export_annotations(current_project,current_folder,saved,writer=fake_writer)
    finally:
        reopened.close()


def test_atomic_new_outputs_originals_preserved_repeated_and_failure(app,workdir,frozen):
    dataset,cfg=frozen
    ledger=book(workdir/"ledger.xlsx",[["001234","要マーク"]])
    folder,session=save_session(app.store.root,dataset,ledger,cfg)
    source=drawing_spec(app.store.root,session)[0]["path"]
    original=Path(source).read_bytes()
    first,report=export_annotations(app.store.root,folder,session,writer=fake_writer)
    second,_=export_annotations(app.store.root,folder,session,writer=fake_writer)
    assert first!=second and report["plan"]["preview"]["config"]["draw_field"]=="temp"
    assert Path(source).read_bytes()==original and ledger.path.read_bytes()==ledger.payload
    with pytest.raises(RuleError,match="新しい"):
        export_annotations(app.store.root,folder,session,writer=fake_writer,output=first)
    def fail(*args):
        fake_writer(*args)
        raise OSError("disk failure")
    with pytest.raises(OSError,match="disk failure"):
        export_annotations(app.store.root,folder,session,writer=fail)
    assert not list(folder.glob(".stage_*")) and len(list(folder.glob("output_*")))==2


def test_cancel_changed_input_during_output_and_lock_are_safe(app,workdir,frozen):
    dataset,cfg=frozen
    ledger=book(workdir/"ledger.xlsx",[["001234","要マーク"]])
    folder,session=save_session(app.store.root,dataset,ledger,cfg)
    cancel=threading.Event()
    def cancelling(*args):
        result=fake_writer(*args)
        cancel.set()
        return result
    with pytest.raises(RuleError,match="キャンセル"):
        export_annotations(app.store.root,folder,session,writer=cancelling,cancel=cancel)
    assert not list(folder.glob("output_*")) and not list(folder.glob(".stage_*"))
    def changing(*args):
        result=fake_writer(*args)
        ledger.path.write_bytes(b"changed")
        return result
    with pytest.raises(RuleError,match="台帳"):
        export_annotations(app.store.root,folder,session,writer=changing)
    assert not list(folder.glob("output_*"))


@pytest.mark.parametrize("action", ["fail", "cancel", "source", "plan"])
def test_final_copy_failure_cancel_and_input_changes_leave_no_completed_output(app,workdir,frozen,monkeypatch,action):
    import dw_workbench.annotation_writer as writer
    dataset,cfg=frozen
    folder,session=save_session(app.store.root,dataset,book(workdir/"ledger.xlsx",[["001234","要マーク"]]),cfg)
    source=Path(drawing_spec(app.store.root,session)[0]["path"])
    original=source.read_bytes()
    cancel=threading.Event()
    copy=writer.shutil.copyfileobj
    def changed(src,dest):
        assert (Path(dest.name).parent/"INCOMPLETE.txt").is_file()
        copy(src,dest)
        if action=="fail":
            raise OSError("final copy failed")
        if action=="cancel":
            cancel.set()
        if action=="source":
            source.write_bytes(b"changed fixed original")
        if action=="plan":
            altered=deepcopy(session)
            altered["created"]="changed while copying"
            (folder/"session.json").write_text(json.dumps(altered),encoding="utf-8")
    monkeypatch.setattr(writer.shutil,"copyfileobj",changed)
    with pytest.raises((OSError,RuleError)):
        export_annotations(app.store.root,folder,session,writer=fake_writer,cancel=cancel)
    assert not list(folder.glob("output_*")) and not list(folder.glob(".stage_*"))
    monkeypatch.setattr(writer.shutil,"copyfileobj",copy)
    source.write_bytes(original)
    save_decisions(folder,session)
    assert export_annotations(app.store.root,folder,session,writer=fake_writer)[0].is_dir()


def test_frozen_dataset_remains_immutable_in_database(app,frozen):
    import sqlite3
    dataset,_=frozen
    with pytest.raises(sqlite3.IntegrityError,match="immutable datasets"):
        app.store.db.execute("UPDATE datasets SET data=? WHERE id=?",("{}",dataset["id"]))
    assert app.dataset(dataset["id"])==dataset


def test_locked_output_rejects_second_writer(app,workdir,frozen):
    from dw_workbench.storage import FileLock
    dataset,cfg=frozen
    folder,session=save_session(app.store.root,dataset,book(workdir/"ledger.xlsx",[["001234","要マーク"]]),cfg)
    lock=FileLock(folder/".output.lock")
    try:
        with pytest.raises(RuleError):
            export_annotations(app.store.root,folder,session,writer=fake_writer)
    finally:
        lock.close()
    assert export_annotations(app.store.root,folder,session,writer=fake_writer)[0].is_dir()


def test_same_anchor_deduplicates_and_exclusions_do_not_modify_adopted_values(app,workdir,frozen):
    dataset,cfg=frozen
    alternate=deepcopy(dataset)
    record=deepcopy(alternate["groups"][0]["records"][0])
    record["id"]="second-record"
    record["fields"]["part"]["value"]="001235"
    alternate["groups"][0]["records"].append(record)
    preview=build_preview(alternate,book(workdir/"ledger.xlsx",[["001234","要マーク"],["001235","要マーク"]]),cfg)
    session=dict(preview=preview,exclusions={})
    marks=drawing_spec(app.store.root,session)[0]["marks"]
    assert len(marks)==1 and len(marks[0]["references"])==2
    assert app.dataset(dataset["id"])==dataset


def test_negative_shared_string_index_is_rejected(workdir):
    import io
    import zipfile
    from xml.etree import ElementTree as ET
    ledger=book(workdir/"ledger.xlsx",[["001234","要マーク"]])
    output=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(ledger.payload)) as src, zipfile.ZipFile(output,"w") as dest:
        for item in src.infolist():
            data=src.read(item.filename)
            if item.filename=="xl/worksheets/sheet1.xml":
                root=ET.fromstring(data)
                ns="{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
                root.find(".//"+ns+"c/"+ns+"v").text="-1"
                data=ET.tostring(root)
            dest.writestr(item,data)
    ledger.path.write_bytes(output.getvalue())
    with pytest.raises(RuleError,match="共有文字列"):
        LedgerBook(ledger.path).sheet("台帳",1)
