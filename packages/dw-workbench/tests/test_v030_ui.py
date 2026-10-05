"""Hidden, subprocess-isolated Tk flows for the multi-document template dialog.

Synthetic invalid XDW bytes and cached blank page images exercise UI and SQLite;
these cases do not execute DocuWorks rendering or GPU OCR.
"""
import functools
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from dw_workbench.domain import ExtractionProfile, PageInfo, Status, identifier
from dw_workbench.ui import MODES
from test_v020_ui import (window, tk_master, make_source, make_profile, select_source, select_page)


def isolated_gui(test):
    @functools.wraps(test)
    def run(request):
        name = request.node.name
        if os.environ.get("DW_WORKBENCH_GUI_CASE") == name:
            test(**{key: request.getfixturevalue(key) for key in inspect.signature(test).parameters})
            print("GUI_FLOW_EXECUTED:"+name)
            return
        environment = os.environ.copy()
        environment.update({"DW_WORKBENCH_GUI_CASE": name, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
        completed = subprocess.run([sys.executable, "-m", "pytest", str(Path(__file__).resolve())+"::"+name,
            "-q", "-s", "-p", "no:cacheprovider"], capture_output=True, text=True, encoding="utf-8",
            env=environment, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        assert completed.returncode == 0, completed.stdout+completed.stderr
        assert "GUI_FLOW_EXECUTED:"+name in completed.stdout
    run.__signature__ = inspect.Signature([inspect.Parameter("request", inspect.Parameter.POSITIONAL_OR_KEYWORD)])
    return run


def choose_profile(dialog, profile):
    dialog.profile_choice.current(next(i for i, p in enumerate(dialog.profiles) if (p.id, p.version) == (profile.id, profile.version)))


def document_profile(app, schema, pages=3):
    profile = ExtractionProfile(identifier(), 1, "文書全体の測定票", tuple(PageInfo(210, 297) for _ in range(pages)), schema.fields,
                                {"part": {"page": 1, "rect": [10, 20, 30, 8]}}, "document", schema.id, schema.version)
    app.register_template(profile, schema)
    return profile


def applied(app, source_id, profile, pages=(1,)):
    app.set_mode(source_id, "page", app.mode(source_id)["revision"])
    return app.assign_pages(source_id, list(pages), profile.id, profile.version, {a.page: a.revision for a in app.assignments(source_id)})


def select_all(dialog):
    dialog.select_all_button.invoke()
    dialog.dialog.update()


@isolated_gui
def test_bulk_multi_document_range_keeps_main_selection_and_starts_no_ocr(window, workdir):
    app = window.app
    first = make_source(app, workdir, pages=3)
    second = make_source(app, workdir, pages=2)
    page_profile, schema = make_profile(app)
    whole = document_profile(app, schema)
    select_source(window, first)
    assert str(window.document_list.cget("selectmode")) == "browse"
    dialog = window.open_bulk_templates()
    assert str(dialog.document_list.cget("selectmode")) == "extended"
    assert dialog.document_list.selection() == (first,)
    assert dialog.document_list.item(first, "values")[0] != dialog.document_list.item(second, "values")[0]
    assert {p.scope for p in dialog.profiles} == {"page", "document"}
    assert "文書用" in window.profile_text(whole)
    assert dialog.unassigned_only.get() is True
    select_all(dialog)
    choose_profile(dialog, page_profile)
    dialog.target_variable.set("ページ範囲")
    dialog.expression_variable.set("2-3")
    plan = dialog.preview()
    assert len(plan.entries) == 4
    assert [(e.page, e.action) for e in plan.entries if e.source_id == second] == [(2, "apply"), (3, "skip")]
    before_jobs = app.store.rows("jobs")
    assert dialog.apply()
    window.root.update()
    assert dialog.result.applied == 3 and dialog.result.skipped == 1
    assert window.document_list.selection() == (first,)
    assert window.source.id == first and window.page == 1 and window.record is None
    assert [a.page for a in app.assignments(first) if a.current_record_id] == [2, 3]
    assert [a.page for a in app.assignments(second) if a.current_record_id] == [2]
    assert app.store.rows("jobs") == before_jobs
    assert "OCRは別操作" in dialog.summary.get()
    assert window.test_errors == []
    dialog.close()


@isolated_gui
def test_bulk_default_protects_accepted_and_excluded_records(window, workdir):
    app = window.app
    first = make_source(app, workdir, pages=3)
    second = make_source(app, workdir, pages=2)
    old, schema = make_profile(app)
    new, _ = make_profile(app, "新しい配置", schema)
    old_id = applied(app, first, old)[0]
    record = app.store.record(old_id)
    from dw_workbench.domain import state_from
    state = state_from(record["data"]["fields"]["part"])
    app.edit(old_id, "part", record["revision"], value="000125", unit="", raw="000125", anchor=state.anchor)
    app.accept(old_id, "part", app.store.record(old_id)["revision"])
    app.exclude_pages(first, [2], "説明だけのページ", {2: 0})
    preserved = app.store.record(old_id)
    select_source(window, first)
    dialog = window.open_bulk_templates()
    select_all(dialog)
    choose_profile(dialog, new)
    plan = dialog.preview()
    assert [e.action for e in plan.entries if e.source_id == first] == ["skip", "skip", "apply"]
    assert dialog.apply()
    window.root.update()
    assert app.store.record(old_id) == preserved
    assert app.assignments(first)[1].state == "excluded" and app.assignments(first)[1].reason == "説明だけのページ"
    assert dialog.result.applied == 3 and dialog.result.skipped == 2
    assert app.store.record(old_id)["data"]["fields"]["part"]["status"] == Status.ACCEPTED
    assert window.test_errors == []
    dialog.close()


@isolated_gui
def test_bulk_document_scope_disables_pages_and_changes_only_unlocked_mode(window, workdir):
    app = window.app
    first = make_source(app, workdir, pages=3)
    second = make_source(app, workdir, pages=3)
    page_profile, schema = make_profile(app)
    whole = document_profile(app, schema)
    preserved_id = applied(app, first, page_profile)[0]
    select_source(window, second)
    dialog = window.open_bulk_templates()
    select_all(dialog)
    choose_profile(dialog, whole)
    assert str(dialog.target_choice.cget("state")) == "disabled"
    assert str(dialog.target_expression.cget("state")) == "disabled"
    assert dialog.targets(whole) == {sid: [0] for sid in dialog.document_list.selection()}
    plan = dialog.preview()
    assert len(plan.mode_changes) == 1 and plan.mode_changes[0].source_id == second
    assert "変更できません" in next(e.reason for e in plan.entries if e.source_id == first)
    assert any("→" in dialog.preview_list.item(row, "values")[-1] for row in dialog.preview_list.get_children())
    assert dialog.apply()
    window.root.update()
    assert app.mode(first)["mode"] == "page" and app.assignments(first)[0].current_record_id == preserved_id
    assert app.mode(second)["mode"] == "document"
    assert app.store.record(app.assignments(second)[0].current_record_id)["page"] is None
    assert window.source.id == second and window.document_list.selection() == (second,)
    assert window.available_profiles == [whole]
    assert window.profile_choice.get() == window.profile_text(whole)
    assert str(window.target_choice.cget("state")) == "disabled"
    assert dialog.result.applied == 1 and dialog.result.skipped == 1 and dialog.result.mode_changes == 1
    assert window.test_errors == []
    dialog.close()


@isolated_gui
def test_bulk_preview_invalidated_by_every_editable_input(window, workdir):
    first = make_source(window.app, workdir)
    second = make_source(window.app, workdir)
    profile, schema = make_profile(window.app)
    other, _ = make_profile(window.app, "別の配置", schema)
    select_source(window, first)
    dialog = window.open_bulk_templates()
    select_all(dialog)
    choose_profile(dialog, profile)
    changes = [lambda: choose_profile(dialog, other), lambda: dialog.target_variable.set("ページ範囲"),
               lambda: dialog.expression_variable.set("2"), lambda: dialog.unassigned_only.set(False),
               lambda: dialog.document_list.selection_set(second)]
    dialog.expression_variable.set("1")
    for change in changes:
        assert dialog.preview() is not None
        assert str(dialog.apply_button.cget("state")) == "normal"
        change()
        dialog.dialog.update()
        assert dialog.plan is None
        assert str(dialog.apply_button.cget("state")) == "disabled"
        assert dialog.preview_list.get_children() == ()
    assert dialog.preview() is not None
    dialog.clear_button.invoke()
    assert dialog.document_list.selection() == () and dialog.plan is None
    assert window.document_list.selection() == (first,)
    assert window.test_errors == []
    dialog.close()


@isolated_gui
def test_bulk_stale_preview_stays_open_and_reconfirmation_is_atomic(window, workdir):
    app = window.app
    first = make_source(app, workdir)
    second = make_source(app, workdir)
    old, schema = make_profile(app)
    new, _ = make_profile(app, "変更後", schema)
    first_id, second_id = applied(app, first, old)[0], applied(app, second, old)[0]
    select_source(window, first)
    dialog = window.open_bulk_templates()
    select_all(dialog)
    choose_profile(dialog, new)
    dialog.target_variable.set("ページ範囲")
    dialog.expression_variable.set("1")
    dialog.unassigned_only.set(False)
    assert dialog.preview() is not None
    app.edit(second_id, "part", app.store.record(second_id)["revision"], value="変更された値", unit="", raw="変更された値", anchor=None)
    assert not dialog.apply()
    assert dialog.dialog.winfo_exists() and dialog.plan is None
    assert str(dialog.apply_button.cget("state")) == "disabled"
    assert "プレビューを作り直して" in dialog.summary.get()
    assert app.assignments(first)[0].current_record_id == first_id
    assert app.assignments(second)[0].current_record_id == second_id
    assert len(window.test_errors) == 1 and "再確認" in window.test_errors[0][0]
    window.test_errors.clear()
    assert dialog.preview() is not None and dialog.apply()
    window.root.update()
    assert not app.store.record(first_id)["active"] and not app.store.record(second_id)["active"]
    assert app.store.record(second_id)["data"]["fields"]["part"]["value"] == "変更された値"
    assert window.source.id == first and window.document_list.selection() == (first,)
    assert window.test_errors == []
    dialog.close()


@isolated_gui
def test_bulk_save_failure_protects_entry_and_apply_inputs(window, workdir):
    app = window.app
    source = make_source(app, workdir)
    old, schema = make_profile(app)
    new, _ = make_profile(app, "変更後", schema)
    old_id = applied(app, source, old)[0]
    select_source(window, source)
    select_page(window, 1)
    window.vars["value"].set("保存できない入力")
    app.store.db.execute("PRAGMA query_only=ON")
    assert window.open_bulk_templates() is None and window.batch_dialog is None
    assert window.dirty and window.vars["value"].get() == "保存できない入力"
    app.store.db.execute("PRAGMA query_only=OFF")
    dialog = window.open_bulk_templates()
    assert not window.dirty and app.store.record(old_id)["data"]["fields"]["part"]["value"] == "保存できない入力"
    choose_profile(dialog, new)
    dialog.target_variable.set("ページ範囲")
    dialog.expression_variable.set("1")
    dialog.unassigned_only.set(False)
    assert dialog.preview() is not None
    window.vars["value"].set("適用前に保持する入力")
    app.store.db.execute("PRAGMA query_only=ON")
    assert not dialog.apply()
    assert window.dirty and window.vars["value"].get() == "適用前に保持する入力"
    assert app.assignments(source)[0].current_record_id == old_id
    assert dialog.dialog.winfo_exists() and "未保存入力を保持" in dialog.summary.get()
    app.store.db.execute("PRAGMA query_only=OFF")
    assert not dialog.apply()  # Saving changed the revision; the preview must be reviewed again.
    assert not window.dirty and dialog.plan is None
    assert app.store.record(old_id)["data"]["fields"]["part"]["value"] == "適用前に保持する入力"
    window.test_errors.clear()
    assert dialog.preview() is not None and dialog.apply()
    window.root.update()
    assert not app.store.record(old_id)["active"]
    assert app.store.record(old_id)["data"]["fields"]["part"]["value"] == "適用前に保持する入力"
    assert window.test_errors == []
    dialog.close()


@isolated_gui
def test_bulk_same_version_noop_and_empty_even_targets(window, workdir):
    app = window.app
    first = make_source(app, workdir, pages=2)
    second = make_source(app, workdir, pages=1)
    profile, _ = make_profile(app)
    old_ids = applied(app, first, profile, pages=(1, 2))
    preserved = [app.store.record(id) for id in old_ids]
    select_source(window, first)
    dialog = window.open_bulk_templates()
    select_all(dialog)
    dialog.unassigned_only.set(False)
    dialog.target_variable.set("偶数ページ")
    plan = dialog.preview()
    assert [(e.page, e.action) for e in plan.entries if e.source_id == second] == [(None, "skip")]
    assert next(e for e in plan.entries if e.source_id == first).action == "same"
    before_jobs = app.store.rows("jobs")
    assert dialog.apply()
    window.root.update()
    assert dialog.result.same == 1 and dialog.result.skipped == 1 and dialog.result.applied == 0
    assert [app.store.record(id) for id in old_ids] == preserved
    assert app.mode(second)["mode"] is None and app.assignments(second) == []
    assert app.store.rows("jobs") == before_jobs
    assert window.test_errors == []
    dialog.close()


@isolated_gui
def test_bulk_application_keeps_readonly_old_result_view(window, workdir):
    app = window.app
    source = make_source(app, workdir)
    old, schema = make_profile(app)
    new, _ = make_profile(app, "変更後", schema)
    old_id = applied(app, source, old)[0]
    select_source(window, source)
    select_page(window, 1)
    window.vars["value"].set("変更前の結果")
    assert window.save_field()
    window.frozen = "archived"
    window.refresh_review()
    window.load_field()
    dialog = window.open_bulk_templates()
    choose_profile(dialog, new)
    dialog.target_variable.set("ページ範囲")
    dialog.expression_variable.set("1")
    dialog.unassigned_only.set(False)
    assert dialog.preview() is not None and dialog.apply()
    window.root.update()
    assert window.frozen == "archived" and window.record["id"] == old_id
    assert window.vars["value"].get() == "変更前の結果"
    assert str(window.entries[0].cget("state")) == "disabled"
    assert window.document_list.selection() == (source,)
    assert app.assignments(source)[0].current_record_id != old_id
    assert window.test_errors == []
    dialog.close()


@isolated_gui
def test_bulk_dialog_small_screen_geometry_and_long_details(window, workdir):
    source = make_source(window.app, workdir)
    make_profile(window.app)
    select_source(window, source)
    dialog = window.open_bulk_templates()
    dialog.dialog.geometry("960x600")
    # A withdrawn Toplevel has no allocated client area (1x1). Allocate its
    # real content frame explicitly, keeping every OS window withdrawn.
    content = dialog.profile_choice.master
    content.pack_forget()
    content.place(x=0, y=0, width=960, height=600)
    dialog.details.set("長い文書名と理由を確認します。"*200)
    dialog.dialog.update_idletasks()
    controls = {}
    for name, widget in (("apply", dialog.apply_button), ("preview", dialog.preview_button),
                         ("source_list", dialog.document_list), ("preview_list", dialog.preview_list),
                         ("details", dialog.detail_text), ("page_choice", dialog.target_choice),
                         ("protection", dialog.unassigned_check)):
        controls[name] = {"x": widget.winfo_rootx()-dialog.dialog.winfo_rootx(), "y": widget.winfo_rooty()-dialog.dialog.winfo_rooty(),
                          "width": widget.winfo_width(), "height": widget.winfo_height()}
    report = {"content_area": [content.winfo_width(), content.winfo_height()], "controls": controls,
              "OS_window_mapped": bool(dialog.dialog.winfo_ismapped()),
              "scope": "Withdrawn Tk content allocated 960x600; widget geometry only, no foreground mapping, screenshot or manual operation acceptance"}
    (workdir/"bulk-layout.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("BULK_DIALOG_GEOMETRY:"+json.dumps(report))
    assert report["content_area"] == [960, 600]
    assert report["OS_window_mapped"] is False
    for box in controls.values():
        assert box["x"] >= 0 and box["y"] >= 0
        assert box["x"]+box["width"] <= 960 and box["y"]+box["height"] <= 600
    assert controls["source_list"]["height"] >= 50 and controls["preview_list"]["height"] >= 50
    assert str(dialog.detail_text.cget("state")) == "disabled"
    assert len(dialog.detail_text.get("1.0", "end")) > 1000
    assert window.test_errors == []
    dialog.close()
