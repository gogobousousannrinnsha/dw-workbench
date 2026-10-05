"""Purpose-based actions, real Tk focus/scroll, recovery and frozen output paths."""
import tkinter as tk
from tkinter import font
import pytest
from dw_workbench.domain import Status
from dw_workbench.ui import Window
from test_v020_ui import (isolated_gui,window,tk_master,make_source,make_profile,
    finish_background,select_source,ledger_dialog_fixture)


@isolated_gui
def test_start_cancel_create_and_resume_without_implicit_actions(window,workdir,monkeypatch,tk_master):
    import dw_workbench.ui as ui
    root=tk.Toplevel(tk_master)
    start=Window(root,workdir/"独立起動")
    finish_background(start)
    try:
        assert start.app is None and start.flow_position.get()=="現在：開始前"
        assert str(start.flow_controls["add"][0].cget("state"))=="disabled"
        start.select_step(5)
        assert start.app is None and "先に" in start.status.get()
        monkeypatch.setattr(ui.simpledialog,"askstring",lambda *a,**k:None)
        start.flow_next.invoke()
        assert start.app is None and not (workdir/"独立起動/projects").exists()
        monkeypatch.setattr(ui.simpledialog,"askstring",lambda *a,**k:"合成 新規案件")
        start.flow_next.invoke()
        finish_background(start)
        assert start.app and "XDW" in start.flow_next.cget("text")
        first=start.app.store.root
        monkeypatch.setattr(ui.filedialog,"askopenfilenames",lambda **k:())
        start.flow_next.invoke()
        assert not start.app.store.rows("sources")
        monkeypatch.setattr(ui.simpledialog,"askstring",lambda *a,**k:"第二の合成案件")
        start.new_project()
        finish_background(start)
        assert start.app.store.root!=first
        monkeypatch.setattr(ui.filedialog,"askdirectory",lambda **k:str(first))
        start.flow_controls["open"][0].invoke()
        finish_background(start)
        assert start.app.store.root==first
    finally:
        start.close()


@isolated_gui
def test_document_template_cancel_ocr_then_manual_review(window,workdir,monkeypatch):
    source=make_source(window.app,workdir,1)
    profile,_=make_profile(window.app)
    select_source(window,source)
    assert "読取設定" in window.flow_next.cget("text")
    before=len(window.app.store.rows("records"))
    monkeypatch.setattr(window,"confirm_list",lambda *a,**k:False)
    window.flow_controls["apply"][0].invoke()
    assert len(window.app.store.rows("records"))==before
    monkeypatch.setattr(window,"confirm_list",lambda *a,**k:True)
    window.flow_controls["apply"][0].invoke()
    window.root.update()
    assert window.record and not window.vars["value"].get()
    assert str(window.accept_button.cget("state"))=="disabled"
    assert "値を入力" in window.flow_reasons["accept"]
    assert "OCRモデル" in window.flow_reasons["ocr"]
    window.caps["models"]=True
    window.select_step(3)
    window.refresh_workflow()
    window.selected_ocr_button.invoke()
    jobs=[r for r in window.app.store.rows("jobs") if r["kind"]=="ocr"]
    assert jobs and all(r["status"]=="pending" for r in jobs)
    assert window.app.store.record(window.record["id"])["data"]["fields"]["part"]["status"]==Status.MISSING
    assert not window.test_errors


@isolated_gui
def test_save_failure_keyboard_confirmation_repeated_press_and_return(window,workdir,monkeypatch):
    source=make_source(window.app,workdir,1)
    profile,_=make_profile(window.app)
    window.app.set_mode(source,"page")
    window.app.assign_pages(source,[1],profile.id,1,{1:0})
    select_source(window,source)
    window.select_step(4)
    window.root.deiconify()
    window.root.update()
    window.vars["value"].set("001234")
    edit=window.app.edit
    monkeypatch.setattr(window.app,"edit",lambda *a,**k:(_ for _ in ()).throw(OSError("合成保存失敗")))
    window.flow_next.invoke()
    assert window.save_failed and window.dirty
    assert "再保存" in window.flow_next.cget("text")
    window.select_step(5)
    assert window.tabs.select()==str(window.review_tab) and window.vars["value"].get()=="001234"
    monkeypatch.setattr(window.app,"edit",edit)
    window.entries[0].focus_force()
    window.root.update()
    window.entries[0].event_generate("<Control-s>")
    assert not window.dirty and not window.save_failed
    assert window.record["data"]["fields"]["part"]["status"]==Status.PENDING
    window.entries[0].focus_force()
    window.root.update()
    accepted=[]
    accept=window.app.accept
    def tracked(*args,**kwargs):
        accepted.append(args)
        return accept(*args,**kwargs)
    monkeypatch.setattr(window.app,"accept",tracked)
    window.entries[0].event_generate("<Control-Return>")
    window.entries[0].event_generate("<Control-Return>")
    assert window.validation_busy and str(window.flow_next.cget("state"))=="disabled"
    finish_background(window)
    assert len(accepted)==1 and window.record["data"]["fields"]["part"]["status"]==Status.ACCEPTED
    window.entries[0].event_generate("<Alt-Key-5>")
    window.root.update()
    assert window.tabs.select()==str(window.output_tab)
    window.finalize_button.event_generate("<Alt-Key-4>")
    assert window.tabs.select()==str(window.review_tab)
    assert not window.test_errors


@isolated_gui
def test_small_enlarged_window_keeps_main_actions_visible_and_scrolls_with_focus(window,workdir):
    source=make_source(window.app,workdir,1)
    profile,_=make_profile(window.app,name="長い読み取りテンプレート名の合成テスト")
    window.app.set_mode(source,"page")
    window.app.assign_pages(source,[1],profile.id,1,{1:0})
    select_source(window,source)
    window.select_step(4)
    window.root.deiconify()
    window.root.geometry("1000x650")
    default=font.nametofont("TkDefaultFont",root=window.root)
    old=default.actual()
    default.configure(size=int(old["size"])+3)
    try:
        window.root.update()
        button=window.accept_button
        assert button.winfo_rooty()+button.winfo_height()<=window.root.winfo_rooty()+window.root.winfo_height()
        assert button.winfo_width()>=button.winfo_reqwidth()
        viewport,content=window.panel_for(window.entries[-1])
        viewport.yview_moveto(0)
        window.entries[-1].focus_force()
        window.root.update()
        assert viewport.yview()[0]>0
        previous=viewport.yview()[0]
        window.entries[-1].event_generate("<Next>")
        assert viewport.yview()[0]>=previous
        window.select_step(5)
        window.root.update()
        assert window.ledger_entry_button.winfo_ismapped()
        assert window.output_reason.get() and window.ledger_reason.get()
    finally:
        default.configure(**old)


@isolated_gui
def test_output_to_ledger_preview_return_condition_change_and_close(window,workdir,monkeypatch):
    import dw_workbench.ledger_ui as lui
    dialog,ledger=ledger_dialog_fixture(window,workdir,monkeypatch)
    assert dialog.panels.select()==str(dialog.preview_tab)
    assert "要確認" in dialog.output_help.get()
    dialog.panels.select(dialog.settings_tab)
    dialog.vars["condition"].set("不要")
    assert "条件が変わって" in dialog.output_help.get()
    assert str(dialog.output_button.cget("state"))=="disabled"
    folder=dialog.folder
    assert dialog.close()
    window.select_step(6)
    window.ledger_entry_button.invoke()
    resumed=window.ledger_dialog
    assert all(pair[0].winfo_exists() for pair in window.scroll_views)
    monkeypatch.setattr(lui.filedialog,"askdirectory",lambda **kw:str(folder))
    resumed.resume()
    assert resumed.vars["condition"].get()=="対象" and not resumed.changed
    row=next(key for key,item in resumed.items.items() if item["scope"]=="record")
    resumed.table.selection_set(row)
    resumed.show_item()
    assert "第1ページ" in resumed.detail.get() and "source_hash" not in resumed.detail.get()
    assert not window.test_errors
