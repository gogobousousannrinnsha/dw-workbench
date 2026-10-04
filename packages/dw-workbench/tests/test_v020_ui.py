"""Real Tk interactions for page templates, independent review and resumable drafts."""
from dataclasses import asdict
from types import SimpleNamespace
import json
import tkinter as tk
from tkinter import ttk
import functools
import inspect
import os
from pathlib import Path
import subprocess
import sys
import pytest
from PIL import Image
from dw_workbench.application import Workbench
from dw_workbench.domain import ExtractionProfile, FieldSchema, PageInfo, ResultSchema, RuleError, identifier
from dw_workbench.ui import Window, target_pages


def isolated_gui(test):
    """Exercise each real GUI flow in a fresh process, just like starting the product."""
    @functools.wraps(test)
    def run(request):
        name = request.node.name
        if os.environ.get("DW_WORKBENCH_GUI_CASE") == name:
            parameters = {key: request.getfixturevalue(key) for key in inspect.signature(test).parameters}
            test(**parameters)
            print("GUI_FLOW_EXECUTED:"+name)
            return
        environment = os.environ.copy()
        environment.update({"DW_WORKBENCH_GUI_CASE": name, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
        completed = subprocess.run([sys.executable, "-m", "pytest", str(Path(__file__).resolve())+"::"+name,
            "-q", "-s", "-p", "no:cacheprovider"], capture_output=True, text=True, encoding="utf-8",
            env=environment, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        assert completed.returncode == 0, completed.stdout+completed.stderr
        assert "GUI_FLOW_EXECUTED:"+name in completed.stdout, "Child did not execute the GUI workflow"
    run.__signature__ = inspect.Signature([inspect.Parameter("request", inspect.Parameter.POSITIONAL_OR_KEYWORD)])
    return run


@pytest.mark.parametrize("choice,selected,expression,expected", [
    ("選択ページ", ["3", "1", "3"], "", [1, 3]),
    ("全ページ", [], "", [1, 2, 3, 4, 5]),
    ("奇数ページ", [], "", [1, 3, 5]),
    ("偶数ページ", [], "", [2, 4]),
    ("ページ範囲", [], "1,3-5", [1, 3, 4, 5]),
    ("ページ範囲", [], "2〜4、5", [2, 3, 4, 5]),
])
def test_bulk_selector(choice, selected, expression, expected):
    assert target_pages(choice, selected, 5, expression) == expected


@pytest.mark.parametrize("expression", ["0", "6", "4-2", "1,", "abc", "1-999999999", ""])
def test_bulk_selector_rejects_invalid_range(expression):
    with pytest.raises(RuleError):
        target_pages("ページ範囲", [], 5, expression)


def make_source(app, workdir, pages=3):
    source = workdir/"synthetic-pages.xdw"
    source.write_bytes(b"GUI unit fixture; not a runtime XDW")
    source_id = app.prepare_source(source)
    app.finish_job("inspect-"+source_id, {"pages": [{"width_mm": 210, "height_mm": 297, "rotation": 0} for _ in range(pages)]})
    from dw_workbench.storage import digest
    for page in range(1, pages+1):
        path = app.store.path(f"cache/{source_id}/page-{page}-150.png")
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1050, 1485), "white").save(path)
        app.finish_job(app.render_job(source_id, page), {"image_sha256": digest(path)})
    return source_id


def make_profile(app, name="測定票A", schema=None, version=1, profile_id=None):
    schema = schema or ResultSchema(identifier(), 1, "共通の測定結果", (FieldSchema("part", "部品番号"),))
    profile = ExtractionProfile(profile_id or identifier(), version, name, (PageInfo(210, 297),), schema.fields,
        {"part": {"page": 1, "rect": [10, 20, 30, 8]}}, "page", schema.id, schema.version)
    app.register_template(profile, schema)
    return profile, schema


def finish_background(window):
    import time
    until = time.monotonic()+10
    while window.background and time.monotonic() < until:
        window.root.update()
        time.sleep(.01)
    assert window.background == 0


@pytest.fixture(scope="module")
def tk_master():
    import gc
    gc.collect()
    master = tk.Tk()
    master.withdraw()
    yield master
    master.destroy()


@pytest.fixture
def window(workdir, monkeypatch, tk_master):
    import dw_workbench.ui as ui
    monkeypatch.setattr(ui, "capabilities", lambda p: {"docuworks": "fixture", "gpu": "なし", "models": False})
    monkeypatch.setattr(Window, "enqueue", lambda self, ids: None)
    # One Tcl interpreter, isolated windows; Tk recommends avoiding multiple Tk roots.
    root = tk.Toplevel(tk_master)
    root.withdraw()
    result = Window(root, workdir, workdir/"projects"/"GUI案件")
    finish_background(result)
    errors = []
    monkeypatch.setattr(ui.messagebox, "showerror", lambda *a, **k: errors.append(a))
    result.test_errors = errors
    try:
        yield result
    finally:
        finish_background(result)
        if result.dirty:
            result.app.store.db.execute("PRAGMA query_only=OFF")
            assert result.save_field()
        result.close()


def select_source(window, source_id):
    window.refresh_lists()
    window.document_list.selection_set(source_id)
    window.select_source()
    window.root.update()


def select_page(window, page):
    window.page_list.selection_set(str(page))
    window.page_list.focus(str(page))
    window.select_page()
    window.select_field()
    window.root.update()


@isolated_gui
def test_page_application_navigation_history_and_frozen_template(window, workdir, monkeypatch):
    app = window.app
    source_id = make_source(app, workdir)
    profile, schema = make_profile(app)
    select_source(window, source_id)
    assert app.mode(source_id)["mode"] == "page"
    monkeypatch.setattr(window, "preview_assignment", lambda pages, profile=None, reason="": True)
    window.target_choice.set("ページ範囲")
    window.target_expression.insert(0, "1-2")
    window.profile_choice.current(0)
    window.apply_profile()
    window.root.update()
    window.select_field()
    first = app.assignments(source_id)[0].current_record_id
    second = app.assignments(source_id)[1].current_record_id
    assert first != second
    assert window.anchor.page == 1
    window.vars["value"].set("001234")
    window.vars["raw"].set("００１２３４")
    window.navigate(1)
    window.root.update()
    window.select_field()
    assert app.store.record(first)["data"]["fields"]["part"]["value"] == "001234"
    assert window.record["id"] == second and window.anchor.page == 2
    assert window.vars["value"].get() == ""
    window.vars["value"].set("009876")
    assert window.save_field()
    app.accept(first, "part", app.store.record(first)["revision"])
    app.accept(second, "part", app.store.record(second)["revision"])
    app.exclude_pages(source_id, [3], "説明ページ", {3: 0})
    dataset_id = app.finalize()
    changed, _ = make_profile(app, "測定票A 改訂", schema, version=2, profile_id=profile.id)
    select_page(window, 2)
    window.target_choice.set("選択ページ")
    window.refresh_lists()
    window.profile_choice.current(next(i for i, p in enumerate(window.available_profiles) if p.version == 2))
    window.apply_profile()
    window.root.update()
    assert window.record["id"] != second
    assert app.store.record(second)["data"]["fields"]["part"]["value"] == "009876"
    assert not app.store.record(second)["active"]
    assert window.record["data"]["fields"]["part"]["value"] == ""
    window.refresh_lists()
    window.history_list.selection_set(dataset_id)
    window.open_history()
    window.history_record.current(1)
    window.select_history_record()
    window.select_field()
    assert window.page == 2 and window.profile.version == 1
    assert window.vars["value"].get() == "009876"
    assert str(window.entries[0].cget("state")) == "disabled"
    assert window.test_errors == []


@isolated_gui
def test_schema_reuse_layout_revision_and_page_relative_range(window, workdir):
    app = window.app
    source_id = make_source(app, workdir)
    original, schema = make_profile(app)
    select_source(window, source_id)
    select_page(window, 2)
    window.new_profile()
    window.schema_choice.current(0)
    window.use_schema()
    window.root.update()
    window.setup_list.selection_set("part")
    window.select_draft_field()
    window.drag_start(SimpleNamespace(x=50, y=100))
    window.drag_end(SimpleNamespace(x=160, y=150))
    assert window.draft_regions["part"]["page"] == 1
    assert window.anchor.page == 2
    window.setup_name.set("配置が違う測定票")
    window.save_profile()
    created = app.profile(window.draft_id, 1)
    assert created.schema_id == schema.id and created.schema_version == 1
    assert created.matches(app.source(source_id), 3)
    window.draft_regions["part"]["rect"] = [11, 21, 35, 9]
    window.draft_changed()
    window.save_profile()
    assert app.profile(created.id, 2).schema_version == 1
    window.draft_fields[0] = FieldSchema("part", "部品番号（必須）")
    window.draft_changed()
    window.save_profile()
    updated = app.profile(created.id, 3)
    assert updated.schema_id == schema.id and updated.schema_version == 2
    assert app.schema(schema.id, 1).fields[0].name == "部品番号"
    assert window.test_errors == []


@isolated_gui
def test_common_template_import_and_draft_resume(window, workdir):
    app = window.app
    source_id = make_source(app, workdir)
    profile, schema = make_profile(app)
    select_source(window, source_id)
    window.publish_choice.current(0)
    window.publish_library()
    destination = workdir/"projects"/"別案件"
    window.open_project(destination)
    window.library_list.selection_set(f"{profile.id}:1")
    window.import_library()
    assert window.app.profile(profile.id, 1) == profile
    window.open_project(app.store.root)
    finish_background(window)
    select_source(window, source_id)
    select_page(window, 3)
    window.new_profile()
    window.setup_name.set("未完了の帳票草案")
    window.draft_fields.append(FieldSchema("draft-field", "手入力予定"))
    window.draft_changed()
    window.checkpoint_draft()
    path = window.app.store.root/"drafts"/"template.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["page"] == 3 and data["source_id"] == source_id
    window.open_project(destination)
    window.open_project(path.parent.parent)
    finish_background(window)
    assert window.draft_dirty and window.setup_name.get() == "未完了の帳票草案"
    assert window.draft_page == 3 and window.draft_fields[0].name == "手入力予定"
    assert window.draft_regions == {}
    assert window.test_errors == []


@isolated_gui
def test_failed_save_keeps_page_and_input(window, workdir, monkeypatch):
    source_id = make_source(window.app, workdir)
    profile, _ = make_profile(window.app)
    select_source(window, source_id)
    window.app.assign_pages(source_id, [1, 2], profile.id, 1, {1: 0, 2: 0})
    select_page(window, 1)
    window.tabs.select(window.review_tab)
    window.root.update()
    window.vars["value"].set("未保存値")
    window.app.store.db.execute("PRAGMA query_only=ON")
    window.navigate(1)
    assert window.page == 1 and window.dirty
    assert window.vars["value"].get() == "未保存値"
    window.app.store.db.execute("PRAGMA query_only=OFF")
    assert window.save_field()
    assert window.test_errors == []


@isolated_gui
def test_v1_copy_migration_is_responsive_and_uses_current_portable(window, workdir, monkeypatch):
    import sqlite3
    import time
    import dw_workbench.storage as storage
    import dw_workbench.ui as ui
    from test_v020_storage import v1_fixture
    original = workdir/"旧Portable"/"projects"/"旧案件"
    original.parent.mkdir(parents=True)
    v1_fixture(original)
    with sqlite3.connect(original/"project.sqlite") as db:
        dataset = json.loads(db.execute("SELECT data FROM datasets").fetchone()[0])
        dataset["created"] = "2026-10-02T12:00:00+00:00"
        db.execute("UPDATE datasets SET data=?", (json.dumps(dataset),))
    original_hash = storage.digest(original/"project.sqlite")
    migrate = storage.migrate_project_copy
    parents = []
    def slow_migrate(path, parent):
        parents.append(parent)
        time.sleep(.08)
        return migrate(path, parent)
    monkeypatch.setattr(storage, "migrate_project_copy", slow_migrate)
    monkeypatch.setattr(ui.messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(ui.messagebox, "showinfo", lambda *a, **k: None)
    responsive = []
    current_source = make_source(window.app, workdir)
    current_profile, _ = make_profile(window.app)
    window.app.set_mode(current_source, "page")
    window.app.assign_pages(current_source, [1], current_profile.id, 1, {1: 0})
    select_source(window, current_source)
    select_page(window, 1)
    window.tabs.select(window.review_tab)
    window.root.update()
    assert str(window.entries[0].cget("state")) == "normal"
    window.root.after(15, lambda: responsive.append(window.validation_busy))
    window.open_project(original)
    assert str(window.entries[0].cget("state")) == "disabled"
    finish_background(window)
    assert responsive == [True]
    assert parents == [window.portable/"projects"]
    assert window.app.store.root.is_relative_to(window.portable/"projects")
    assert not window.app.store.root.is_relative_to(original.parent)
    assert storage.digest(original/"project.sqlite") == original_hash
    assert window.app.mode("source")["mode"] == "document"
    assert window.app.store.record("record")["data"]["fields"]["part"]["value"] == "001234"
    assert window.test_errors == []


def click_confirmation(window, captured, label):
    def visit(widget):
        if isinstance(widget, tk.Text):
            captured.append(widget.get("1.0", "end-1c"))
        if isinstance(widget, ttk.Button) and widget.cget("text") == label:
            widget.invoke()
            return True
        for child in list(widget.winfo_children()):
            if visit(child):
                return True
        return False
    dialogs = [child for child in window.root.winfo_children() if isinstance(child, tk.Toplevel)]
    assert len(dialogs) == 1
    assert visit(dialogs[0]), "Confirmation action not found"


@isolated_gui
def test_actual_preview_same_version_exclusion_and_archived_view(window, workdir, monkeypatch):
    import dw_workbench.ui as ui
    app = window.app
    source_id = make_source(app, workdir)
    profile, _ = make_profile(app)
    app.set_mode(source_id, "page")
    app.assign_pages(source_id, [1, 2, 3], profile.id, 1, {1: 0, 2: 0, 3: 0})
    select_source(window, source_id)
    select_page(window, 1)
    window.vars["value"].set("001234")
    assert window.save_field()
    record = app.store.record(window.record["id"])
    captured = []
    window.target_choice.set("全ページ")
    window.profile_choice.current(0)
    window.root.after(20, lambda: click_confirmation(window, captured, "適用する"))
    window.apply_profile()
    assert len(captured) == 1 and captured[0].count("同じ版・変更なし") == 3
    assert app.store.record(record["id"]) == record
    window.target_choice.set("選択ページ")
    select_page(window, 2)
    previous_id = window.record["id"]
    monkeypatch.setattr(ui.simpledialog, "askstring", lambda *a, **k: "説明ページ")
    window.root.after(20, lambda: click_confirmation(window, captured, "適用する"))
    window.exclude_pages()
    assert app.assignments(source_id)[1].reason == "説明ページ"
    assert not app.store.record(previous_id)["active"]
    assert "対象外: 説明ページ" in captured[-1]
    window.open_assignment_history()
    dialog = next(child for child in window.root.winfo_children() if isinstance(child, tk.Toplevel))
    listing = next(child for child in dialog.winfo_children() if isinstance(child, ui.ttk.Treeview))
    listing.selection_set(previous_id)
    button = next(child for child in dialog.winfo_children() if isinstance(child, ui.ttk.Button))
    button.invoke()
    window.select_field()
    assert window.frozen == "archived" and window.record["id"] == previous_id
    assert str(window.entries[0].cget("state")) == "disabled"
    assert window.page == 2 and window.anchor.page == 2
    assert window.test_errors == []


@isolated_gui
def test_this_record_ocr_excludes_unrelated_pending_and_resume_restores_it(window, workdir, monkeypatch):
    app = window.app
    source_id = make_source(app, workdir)
    profile, _ = make_profile(app)
    app.set_mode(source_id, "page")
    records = app.assign_pages(source_id, [1, 2], profile.id, 1, {1: 0, 2: 0})
    unrelated_job = app.ocr_jobs(records[1])[0]
    select_source(window, source_id)
    select_page(window, 1)
    captured = []
    monkeypatch.setattr(window, "enqueue", lambda ids: captured.append(list(ids)))
    window.run_ocr()
    assert len(captured) == 1 and unrelated_job not in captured[0]
    assert {app.job(id)["kind"] for id in captured[0]} == {"render", "ocr"}
    assert all(app.job(id)["data"].get("record_id", records[0]) == records[0] for id in captured[0])
    window.tasks = list(captured[0])
    window.cancel_jobs()
    assert not window.tasks and "中断しました" in window.status.get()
    window.resume_jobs()
    assert unrelated_job in captured[-1]
    assert window.test_errors == []


@isolated_gui
def test_incomplete_output_scroll_list_decline_and_confirmed_case_export(window, workdir, monkeypatch):
    app = window.app
    source_id = make_source(app, workdir)
    profile, _ = make_profile(app)
    app.set_mode(source_id, "page")
    record_id = app.assign_pages(source_id, [1], profile.id, 1, {1: 0})[0]
    select_source(window, source_id)
    select_page(window, 1)
    window.vars["value"].set("001234")
    assert window.save_field()
    window.accept()
    finish_background(window)
    captured = []
    window.root.after(20, lambda: click_confirmation(window, captured, "戻る"))
    window.finalize()
    assert app.store.rows("datasets") == []
    assert "p2" in captured[-1] and "p3" in captured[-1]
    window.root.after(20, lambda: click_confirmation(window, captured, "完了分だけ出力"))
    window.finalize()
    finish_background(window)
    datasets = app.store.rows("datasets")
    assert len(datasets) == 1
    dataset = app.dataset(datasets[0]["id"])
    assert dataset["format_version"] == 2
    assert dataset["groups"][0]["records"][0]["id"] == record_id
    assert {r["page"] for r in dataset["excluded"]} == {2, 3}
    artifacts = app.store.rows("artifacts")
    assert len(artifacts) == 2 and all(a["status"] == "complete" for a in artifacts)
    assert any(a["name"].endswith("案件結果.xlsx") for a in artifacts)
    assert window.test_errors == []


@isolated_gui
def test_document_mode_template_authoring_and_lock_after_assignment(window, workdir):
    import dw_workbench.ui as ui
    source_id = make_source(window.app, workdir)
    make_profile(window.app)
    select_source(window, source_id)
    assert window.app.mode(source_id)["mode"] == "page"
    window.mode_choice.set(ui.MODES["document"])
    window.change_mode()
    assert window.app.mode(source_id)["mode"] == "document"
    assert [a.page for a in window.app.assignments(source_id)] == [0]
    assert window.available_profiles == []
    assert str(window.target_choice.cget("state")) == "disabled"
    window.new_profile()
    assert window.setup_scope.get() == "文書全体用"
    window.draft_fields = [FieldSchema("whole-document", "文書全体の項目")]
    window.refresh_draft()
    window.setup_list.selection_set("whole-document")
    window.root.update()
    window.navigate(1)
    assert window.page == 2
    window.drag_start(SimpleNamespace(x=50, y=100))
    window.drag_end(SimpleNamespace(x=160, y=150))
    assert window.draft_regions["whole-document"]["page"] == 2
    window.save_profile()
    profile = window.app.profile(window.draft_id, 1)
    assert profile.scope == "document" and len(profile.pages) == 3
    window.profile_choice.current(0)
    captured = []
    window.root.after(20, lambda: click_confirmation(window, captured, "適用する"))
    window.apply_profile()
    window.select_field()
    assert window.record["page"] is None and window.anchor.page == 2
    assert str(window.mode_choice.cget("state")) == "disabled"
    window.mode_choice.set(ui.MODES["page"])
    with pytest.raises(RuleError, match="変更できません"):
        window.change_mode()
    assert window.app.mode(source_id)["mode"] == "document"
    assert window.test_errors == []


@isolated_gui
def test_export_history_save_failure_keeps_results_then_retries_without_regeneration(window, workdir, monkeypatch):
    import dw_workbench.exporting as exporting
    from dw_workbench.storage import digest
    app = window.app
    source_id = make_source(app, workdir)
    profile, _ = make_profile(app)
    app.set_mode(source_id, "page")
    app.assign_pages(source_id, [1], profile.id, 1, {1: 0})
    select_source(window, source_id)
    select_page(window, 1)
    window.vars["value"].set("001234")
    assert window.save_field()
    window.accept()
    finish_background(window)
    dataset_id = app.finalize(completed_only=True)
    generation_calls = []
    generate = exporting.generate_artifacts
    def tracked_generation(*args, **kwargs):
        generation_calls.append(args[1]["id"])
        return generate(*args, **kwargs)
    monkeypatch.setattr(exporting, "generate_artifacts", tracked_generation)
    app.store.db.execute("PRAGMA query_only=ON")
    window.export(dataset_id)
    with pytest.raises(RuleError, match="出力中"):
        window.export(dataset_id)
    finish_background(window)
    assert dataset_id in window.pending_exports
    assert window.history_list.exists(dataset_id)
    dataset, results = window.pending_exports[dataset_id]
    assert dataset["id"] == dataset_id
    assert len(results) == 2 and all(r["status"] == "complete" for r in results)
    assert app.store.rows("artifacts") == []
    assert "保存失敗" in window.status.get() and "出力完了" not in window.status.get()
    files = [app.store.path(r["path"]) for r in results]
    original_files = [(str(file), digest(file), file.stat().st_mtime_ns) for file in files]
    assert not window.retry_saves()
    assert dataset_id in window.pending_exports
    window.close()
    assert not window.closing and window.root.winfo_exists()
    assert len(window.test_errors) == 1
    window.test_errors.clear()
    app.store.db.execute("PRAGMA query_only=OFF")
    assert window.retry_saves()
    assert not window.pending_exports
    assert generation_calls == [dataset_id]
    assert [(str(file), digest(file), file.stat().st_mtime_ns) for file in files] == original_files
    assert len(app.store.rows("artifacts")) == 2
    assert all(a["status"] == "complete" for a in app.store.rows("artifacts"))
    assert "出力完了" in window.status.get()
    assert window.test_errors == []


@isolated_gui
def test_ocr_callback_keeps_dirty_input_and_candidate_selection_without_project_scan(window, workdir, monkeypatch):
    app = window.app
    first_source = make_source(app, workdir)
    second_source = make_source(app, workdir)
    profile, _ = make_profile(app)
    for source in (first_source, second_source):
        app.set_mode(source, "page")
        app.assign_pages(source, [1, 2, 3], profile.id, 1, {1: 0, 2: 0, 3: 0})
    select_source(window, first_source)
    select_page(window, 1)
    window.tabs.select(window.review_tab)
    window.root.update()
    record_id = window.record["id"]
    def candidate(text):
        job_id = app.ocr_jobs(record_id)[0]
        app.start_job(job_id)
        app.finish_job(job_id, result={"text": text, "regions": [{"text": text, "confidence": .9,
            "polygon_mm": [[10, 20], [40, 20], [40, 28], [10, 28]]}], "engine": {"name": "synthetic fixture"}})
        return app.job(job_id)
    first_job = candidate("OCR候補1")
    window.refresh_job_view(first_job)
    chosen_candidate = window.candidate_values[window.candidate_list.current()]["id"]
    window.vars["value"].set("保存前の訂正")
    window.vars["raw"].set("原文は保持")
    anchor_before = asdict(window.anchor)
    document_before = window.document_list.item(first_source, "values")
    second_job = candidate("OCR候補2")
    queries = []
    app.store.db.set_trace_callback(queries.append)
    window.refresh_job_view(second_job)
    app.store.db.set_trace_callback(None)
    assert len(queries) == 1 and "FROM candidates" in queries[0]
    assert window.dirty and window.vars["value"].get() == "保存前の訂正"
    assert window.vars["raw"].get() == "原文は保持"
    assert asdict(window.anchor) == anchor_before
    assert window.candidate_values[window.candidate_list.current()]["id"] == chosen_candidate
    assert "候補2件" in window.candidate_count_label.cget("text")
    assert window.document_list.item(first_source, "values") == document_before
    other_records = {a.current_record_id for a in app.assignments(second_source)}
    queried_records = []
    original_context = app.context
    def tracked_context(id):
        queried_records.append(id)
        return original_context(id)
    monkeypatch.setattr(app, "context", tracked_context)
    monkeypatch.setattr(window, "refresh_lists", lambda: pytest.fail("A field edit must not scan the whole project"))
    assert window.save_field()
    assert other_records.isdisjoint(queried_records)
    window.accept()
    finish_background(window)
    assert window.document_list.item(first_source, "values")[1] == "1/3 記録 完了"
    assert window.page_list.item("1", "values")[2] == "1/1 項目 完了"
    assert window.test_errors == []
