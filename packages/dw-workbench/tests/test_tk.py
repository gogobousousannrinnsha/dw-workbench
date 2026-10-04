"""Automated Tk widget interaction; distinct from on-site manual acceptance."""
from dataclasses import asdict
import json
from pathlib import Path
import tkinter as tk
from types import SimpleNamespace
from PIL import Image
from dw_workbench.domain import ExtractionProfile, FieldSchema, PageInfo, identifier, Status
from dw_workbench.ui import Window


def drain(root, window):
    import time
    deadline = time.monotonic()+10
    while window.background and time.monotonic() < deadline:
        root.update()
        time.sleep(.01)
    assert window.background == 0


def test_tk_manual_save_zoom_scroll_frozen_and_save_failure(workdir, monkeypatch):
    root = tk.Tk()
    root.withdraw()
    window = Window(root, workdir, workdir/"projects/GUI 案件")
    try:
        file = workdir/"synthetic.xdw"
        file.write_bytes(b"GUI fixture - not runtime XDW")
        app = window.app
        id = app.prepare_source(file)
        app.finish_job("inspect-"+id, {"pages": [{"width_mm": 210, "height_mm": 297, "rotation": 0}]})
        p = ExtractionProfile(identifier(), 1, "GUI", (PageInfo(210, 297),), (FieldSchema("part", "部品"),), {"part": {"page": 1, "rect": [10, 20, 30, 8]}})
        app.register_profile(p)
        rid = app.apply_profile(id, p.id, 1)
        image = app.store.path(f"cache/{id}/page-1-150.png")
        image.parent.mkdir(parents=True)
        Image.new("RGB", (1050, 1485), "white").save(image)
        from dw_workbench.storage import digest
        app.finish_job(app.render_job(id, 1), {"image_sha256": digest(image)})
        window.refresh_lists()
        window.document_list.selection_set(id)
        window.select_source()
        window.select_field()
        window.tabs.select(window.review_tab)
        root.update()
        window.vars["value"].set("001234")
        window.vars["raw"].set("００１２３４")
        assert window.save_field()
        import dw_workbench.storage as storage
        import time
        original_validate = storage.validate_sources
        def slow_validate(*args):
            time.sleep(.15)
            return original_validate(*args)
        monkeypatch.setattr(storage, "validate_sources", slow_validate)
        responsive = []
        root.after(20, lambda: responsive.append(window.validation_busy))
        window.accept()
        drain(root, window)
        assert responsive == [True]
        monkeypatch.setattr(storage, "validate_sources", original_validate)
        assert app.store.record(rid)["data"]["fields"]["part"]["status"] == Status.ACCEPTED
        before = asdict(window.anchor)
        window.zoom.set("200%")
        window.show_image()
        window.canvas.xview_moveto(.05)
        window.canvas.yview_moveto(.08)
        assert asdict(window.anchor) == before
        # Click-drag uses canvas scrolling coordinates, not window positions.
        window.drag_start(SimpleNamespace(x=40, y=50))
        window.drag_end(SimpleNamespace(x=140, y=90))
        assert window.anchor.rect != tuple(before["rect"])
        assert window.save_field()
        assert app.store.record(rid)["data"]["fields"]["part"]["status"] == Status.PENDING
        window.accept()
        drain(root, window)
        dataset = app.finalize()
        window.refresh_lists()
        window.history_list.selection_set(dataset)
        window.open_history()
        window.select_field()
        assert window.frozen == dataset
        assert str(window.entries[0].cget("state")) == "disabled"
        window.document_list.selection_set(id)
        window.select_source()
        window.select_field()
        app.store.db.execute("PRAGMA query_only=ON")
        window.vars["value"].set("unsaved")
        assert not window.save_field()
        assert window.dirty and window.vars["value"].get() == "unsaved"
        assert "保存失敗" in window.save_label.cget("text")
        app.store.db.execute("PRAGMA query_only=OFF")
        assert window.save_field()
        assert not window.dirty
        job = app.ocr_jobs(rid)[0]
        app.start_job(job)
        value = {"text": "", "regions": [], "engine": {}}
        window.pending_results[job] = (value, False)
        app.store.db.execute("PRAGMA query_only=ON")
        assert not window.retry_saves()
        assert job in window.pending_results
        app.store.db.execute("PRAGMA query_only=OFF")
        assert window.retry_saves()
        assert not window.pending_results
        assert app.job(job)["status"] == "complete"
        invalid = workdir/"invalid.xdw"
        invalid.write_bytes(b"fixture")
        failed = app.prepare_source(invalid)
        app.finish_job("inspect-"+failed, error="fixture refused")
        window.refresh_lists()
        window.document_list.selection_set("job-inspect-"+failed)
        window.select_source()
        assert window.source is None and window.record is None
        assert str(window.entries[0].cget("state")) == "disabled"
    finally:
        import time
        deadline = time.monotonic()+10
        while window.background and time.monotonic() < deadline:
            root.update()
            time.sleep(.01)
        window.close()
