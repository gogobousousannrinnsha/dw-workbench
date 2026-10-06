"""Continuous review through dimension mismatches using real Tk widgets."""
from dataclasses import replace
from PIL import Image
from dw_workbench.storage import digest
from test_v020_ui import (isolated_gui, window, tk_master, finish_background,
    make_profile, select_source, select_page)


def mixed_source(app, workdir, dimensions=((210, 297), (297, 420), (210, 297))):
    path = workdir / 'synthetic-mixed-dimensions.xdw'
    path.write_bytes(b'Synthetic unit bytes; not a runtime XDW')
    sid = app.prepare_source(path)
    app.finish_job('inspect-' + sid, {'pages': [dict(width_mm=w, height_mm=h, rotation=0) for w, h in dimensions]})
    for number, _ in enumerate(dimensions, 1):
        image = app.store.path(f'cache/{sid}/page-{number}-150.png')
        image.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (1050, 1485), 'white').save(image)
        app.finish_job(app.render_job(sid, number), {'image_sha256': digest(image)})
    return sid


@isolated_gui
def test_ocr_flow_button_skips_mismatch_without_modal_and_moves_forward(window, workdir):
    sid = mixed_source(window.app, workdir)
    profile, _ = make_profile(window.app)
    window.app.set_mode(sid, 'page')
    records = window.app.assign_pages(sid, [1, 2, 3], profile.id, 1, {1: 0, 2: 0, 3: 0})
    select_source(window, sid)
    select_page(window, 2)
    window.target_choice.set('全ページ')
    window.caps['models'] = True
    window.tabs.select(window.review_tab)
    window.root.update()
    window.refresh_workflow()
    window.flow_next.invoke()
    window.root.update()
    assert not window.test_errors
    assert window.record['id'] == records[2]
    assert 'スキップ' in window.status.get()
    assert not [job for job in window.app.store.rows('jobs') if job['kind'] == 'ocr']


@isolated_gui
def test_direct_and_batch_ocr_skip_without_modal_and_leave_unassigned(window, workdir):
    sid = mixed_source(window.app, workdir)
    profile, _ = make_profile(window.app)
    window.app.set_mode(sid, 'page')
    records = window.app.assign_pages(sid, [1, 2], profile.id, 1, {1: 0, 2: 0})
    select_source(window, sid)
    select_page(window, 2)
    window.safe(window.run_ocr)
    window.root.update()
    assert window.page == 3 and window.record is None  # unassigned stays pending
    assert not window.test_errors
    select_page(window, 2)
    window.target_choice.set('全ページ')
    window.safe(window.run_selected_ocr)
    window.root.update()
    jobs = [window.app.job(j['id']) for j in window.app.store.rows('jobs') if j['kind'] == 'ocr']
    assert len(jobs) == 1 and jobs[0]['data']['record_id'] == records[0]
    assert '寸法不一致 1' in window.status.get() and '未選択・対象外 1' in window.status.get()
    assert window.app.assignments(sid)[2].state == 'unassigned'
    assert not window.test_errors


@isolated_gui
def test_all_mismatch_no_jobs_no_modal_nonmodal_details_and_reassignment(window, workdir):
    from dw_workbench.domain import PageInfo, identifier
    from tkinter import ttk
    sid = mixed_source(window.app, workdir, dimensions=((297, 420), (297, 420)))
    profile, schema = make_profile(window.app)
    window.app.set_mode(sid, 'page')
    records = window.app.assign_pages(sid, [1, 2], profile.id, 1, {1: 0, 2: 0})
    select_source(window, sid)
    select_page(window, 1)
    window.target_choice.set('全ページ')
    window.caps['models'] = True
    for action in (window.run_ocr, window.run_selected_ocr, window.next_unfinished):
        window.safe(action)
        window.root.update()
        assert window.record['id'] == records[0]
        assert 'スキップ' in window.status.get()
    assert not window.test_errors
    assert not [job for job in window.app.store.rows('jobs') if job['kind'] == 'ocr']
    window.refresh_workflow()
    assert '選び直す' in window.flow_next.cget('text')
    assert window.workflow_counts()['unconfirmed'] == 0
    assert window.workflow_counts()['skipped'] == 2
    window.show_workflow_skips()
    window.root.update()
    assert window.root.grab_current() is None
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)
    table = next(w for w in descendants(window.skip_dialog) if isinstance(w, ttk.Treeview))
    assert len(table.get_children()) == 2
    assert len([w for w in descendants(window.skip_dialog) if isinstance(w, ttk.Scrollbar)]) == 2
    window.skip_dialog.destroy()  # cancellation does not touch assignments
    fit = replace(profile, id=identifier(), name='適合A3', pages=(PageInfo(297, 420),))
    window.app.register_template(fit, schema)
    newer = window.app.assign_pages(sid, [1], fit.id, 1, {1: 1})[0]
    window.refresh_lists()
    select_page(window, 1)
    window.tabs.select(window.review_tab)
    window.root.update()
    window.refresh_workflow()
    assert window.record['id'] == newer
    assert window.workflow_counts()['skipped'] == 1
    assert window.workflow_counts()['unconfirmed'] == 1
    window.safe(window.run_ocr)
    assert [j for j in window.app.store.rows('jobs') if j['kind'] == 'ocr']
    assert not window.test_errors


@isolated_gui
def test_continuous_review_saves_manual_draft_then_wraps_and_unknown_errors_surface(window, workdir, monkeypatch):
    sid = mixed_source(window.app, workdir)
    profile, _ = make_profile(window.app)
    window.app.set_mode(sid, 'page')
    records = window.app.assign_pages(sid, [1, 2, 3], profile.id, 1, {1: 0, 2: 0, 3: 0})
    select_source(window, sid)
    select_page(window, 2)
    window.vars['value'].set('手入力を保持')
    window.safe(window.run_ocr)
    window.root.update()
    assert window.record['id'] == records[2]
    assert window.app.store.record(records[1])['data']['fields']['part']['value'] == '手入力を保持'
    window.vars['value'].set('001234')
    window.accept()
    finish_background(window)
    window.next_unfinished()
    window.root.update()
    assert window.record['id'] == records[0]
    window.vars['value'].set('001235')
    window.accept()
    finish_background(window)
    window.next_unfinished()
    window.root.update()
    assert '通常対象の未完了はありません' in window.status.get()
    assert window.workflow_counts()['complete_records'] == 2
    assert window.workflow_counts()['skipped'] == 1
    def unexpected(*args):
        raise OSError('synthetic unexpected failure')
    monkeypatch.setattr(window.app, 'ocr_jobs', unexpected)
    window.safe(window.run_ocr)
    assert len(window.test_errors) == 1 and 'synthetic unexpected failure' in str(window.test_errors[0])


@isolated_gui
def test_save_failure_keeps_dirty_mismatch_and_blocks_navigation_until_retry(window, workdir):
    sid = mixed_source(window.app, workdir)
    profile, _ = make_profile(window.app)
    window.app.set_mode(sid, 'page')
    records = window.app.assign_pages(sid, [1, 2, 3], profile.id, 1, {1: 0, 2: 0, 3: 0})
    select_source(window, sid)
    select_page(window, 2)
    window.vars['value'].set('保存待ち')
    window.app.store.db.execute('PRAGMA query_only=ON')
    window.safe(window.run_ocr)
    window.root.update()
    assert window.record['id'] == records[1] and window.dirty
    assert window.vars['value'].get() == '保存待ち'
    window.app.store.db.execute('PRAGMA query_only=OFF')
    window.test_errors.clear()
    window.safe(window.run_ocr)
    window.root.update()
    assert window.record['id'] == records[2]
    assert window.app.store.record(records[1])['data']['fields']['part']['value'] == '保存待ち'
    assert not window.test_errors
