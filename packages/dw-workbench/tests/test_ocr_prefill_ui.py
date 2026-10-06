"""Real Tk foreground review, background ownership and confirm-next behavior."""
from threading import Event
import json
import time
from PIL import Image
from dw_workbench.domain import Anchor, Status, ExtractionProfile, FieldSchema, ResultSchema, PageInfo, identifier
from dw_workbench.storage import digest
from dw_workbench.ui import Window
from test_ocr_prefill import result
from test_dimension_skip_ui import mixed_source
from test_v020_ui import (isolated_gui, window, tk_master, make_source, make_profile,
    select_source, select_page, finish_background)

REAL_ENQUEUE = Window.enqueue


def setup(window, workdir, *, mixed=False):
    window.root.deiconify()
    window.root.geometry('1200x780')
    window.root.focus_force()
    window.root.update()
    sid = mixed_source(window.app, workdir) if mixed else make_source(window.app, workdir, 3)
    profile, _ = make_profile(window.app)
    window.app.set_mode(sid, 'page')
    records = window.app.assign_pages(sid, [1, 2, 3], profile.id, 1, {1: 0, 2: 0, 3: 0})
    select_source(window, sid)
    select_page(window, 1)
    window.caps['models'] = True
    return sid, profile, records


def deliver(window, job, text='001234', error=False):
    assert window.persist_worker_result(job, text if error else result(text), error)
    window.refresh_job_view(job)
    window.root.update()


@isolated_gui
def test_apply_ocr_prefill_focus_then_one_confirm_advances(window, workdir, monkeypatch):
    window.root.deiconify()
    window.root.geometry('1200x780')
    window.root.focus_force()
    window.root.update()
    sid = make_source(window.app, workdir, 3)
    profile, _ = make_profile(window.app)
    select_source(window, sid)
    window.target_choice.set('全ページ')
    monkeypatch.setattr(window, 'confirm_list', lambda *a, **k: True)
    window.apply_profile()
    window.root.update()
    window.caps['models'] = True
    rid = window.record['id']
    window.run_ocr()
    job = window.app.latest_ocr(rid, 'part')
    deliver(window, window.app.job(job['id']), '000125')
    assert window.tabs.select() == str(window.review_tab)
    assert window.vars['value'].get() == '000125'
    assert window.root.focus_get() == window.entries[0]
    assert '未確認' in window.save_label.cget('text')
    assert window.app.store.record(rid)['data']['fields']['part']['status'] == Status.PENDING
    assert window.flow_next.cget('text') == '確認して次へ'
    window.accept_button.invoke()
    finish_background(window)
    window.root.update()
    assert window.app.store.record(rid)['data']['fields']['part']['status'] == Status.ACCEPTED
    assert window.page == 2 and window.field_id == 'part'
    assert not window.test_errors


@isolated_gui
def test_background_other_document_never_changes_screen_or_dirty_input(window, workdir):
    sid, profile, records = setup(window, workdir)
    window.run_ocr()
    job = window.app.job(window.app.latest_ocr(records[0], 'part')['id'])
    other = make_source(window.app, workdir, 1)
    window.app.set_mode(other, 'page')
    other_rid = window.app.assign_pages(other, [1], profile.id, 1, {1: 0})[0]
    select_source(window, other)
    select_page(window, 1)
    window.tabs.select(window.review_tab)
    window.root.update()
    window.vars['value'].set('入力中の別文書')
    window.entries[0].focus_force()
    window.root.update()
    context = window.review_context()
    deliver(window, job)
    assert window.review_context() == context and window.record['id'] == other_rid
    assert window.vars['value'].get() == '入力中の別文書'
    assert window.root.focus_get() == window.entries[0]
    assert window.app.store.record(records[0])['data']['fields']['part']['value'] == '001234'
    assert not window.test_errors


@isolated_gui
def test_real_async_callback_saves_human_edit_and_cancel_ignores_late_response(window, workdir, monkeypatch):
    sid, _, records = setup(window, workdir)
    image = window.app.store.path(f'cache/{sid}/page-1-300.png')
    Image.new('RGB', (2100, 2970), 'white').save(image)
    window.app.finish_job(window.app.render_job(sid, 1, 300), {'image_sha256': digest(image)})
    class Client:
        def __init__(self):
            self.called, self.release = Event(), Event()
        def call(self, request):
            self.called.set()
            assert self.release.wait(10)
            return result()
        def close(self):
            self.release.set()
    client = Client()
    window.clients['ocr'] = client
    monkeypatch.setattr(window, 'enqueue', lambda ids: REAL_ENQUEUE(window, ids))
    def started():
        deadline = time.monotonic()+5
        while not client.called.is_set() and time.monotonic() < deadline:
            window.root.update()
            time.sleep(.01)
        assert client.called.is_set()
    window.run_ocr()
    started()
    job_id = window.active_job
    window.vars['value'].set('人の訂正')
    window.vars['raw'].set('原文の転記')
    window.anchor = Anchor(sid, window.app.source(sid).sha256, 1, (12, 22, 24, 8))
    window.changed()
    client.release.set()
    finish_background(window)
    field = window.app.store.record(records[0])['data']['fields']['part']
    assert field['value'] == '人の訂正' and field['raw'] == '原文の転記'
    assert field['anchor']['rect'] == [12, 22, 24, 8]
    assert json.loads(window.app.job(job_id)['result'])['prefill']['status'] == 'protected'
    assert window.vars['value'].get() == '人の訂正' and not window.dirty
    count = len(window.app.candidates(records[0], 'part'))
    client.called.clear()
    client.release.clear()
    window.run_ocr()
    started()
    cancelled = window.active_job
    window.cancel_jobs()
    finish_background(window)
    assert window.app.job(cancelled)['status'] == 'failed'
    assert len(window.app.candidates(records[0], 'part')) == count
    assert window.vars['value'].get() == '人の訂正'
    assert not window.test_errors


@isolated_gui
def test_save_failure_holds_response_until_retry_without_overwriting_clear(window, workdir):
    _, _, records = setup(window, workdir)
    window.run_ocr()
    job = window.app.job(window.app.latest_ocr(records[0], 'part')['id'])
    window.vars['value'].set('')  # Explicit user clear, even if initially empty.
    window.app.store.db.execute('PRAGMA query_only=ON')
    assert not window.persist_worker_result(job, result())
    assert window.dirty and not window.app.candidates(records[0], 'part')
    window.pending_results[job['id']] = (result(), False)
    window.app.store.db.execute('PRAGMA query_only=OFF')
    assert window.retry_saves()
    assert window.app.store.record(records[0])['data']['fields']['part']['value'] == ''
    assert window.app.input_origin(records[0], 'part') == 'human'
    assert json.loads(window.app.job(job['id'])['result'])['prefill']['status'] == 'protected'
    assert not window.pending_results


@isolated_gui
def test_batch_prefill_and_confirm_next_keep_dimension_skip(window, workdir):
    sid, _, records = setup(window, workdir, mixed=True)
    window.target_choice.set('全ページ')
    window.run_selected_ocr()
    jobs = [window.app.job(j['id']) for j in window.app.store.rows('jobs') if j['kind'] == 'ocr']
    assert len(jobs) == 2
    for job in jobs:
        deliver(window, job, '00100'+str(job['data']['page']))
    assert window.record['id'] == records[0]
    assert window.vars['value'].get() == '001001'
    window.accept_button.invoke()
    finish_background(window)
    window.root.update()
    assert window.record['id'] == records[2] and window.vars['value'].get() == '001003'
    assert window.app.store.record(records[1])['data']['fields']['part']['value'] == ''
    assert window.workflow_counts()['skipped'] == 1
    assert not window.test_errors


@isolated_gui
def test_foreground_failed_ocr_opens_review_without_filling_or_repeating(window, workdir):
    _, _, records = setup(window, workdir)
    window.tabs.select(window.list_tab)
    window.root.update()
    window.run_ocr()
    job = window.app.job(window.app.latest_ocr(records[0], 'part')['id'])
    deliver(window, job, 'synthetic read failure', error=True)
    assert window.tabs.select() == str(window.review_tab)
    assert window.vars['value'].get() == ''
    assert '読取失敗' in window.candidate_count_label.cget('text')
    assert window.ocr_review_request is None
    assert not window.test_errors


@isolated_gui
def test_foreground_second_field_remains_selected_across_review_tab_change(window, workdir):
    window.root.deiconify()
    window.root.focus_force()
    sid = make_source(window.app, workdir, 1)
    schema = ResultSchema(identifier(), 1, '合成二項目', (FieldSchema('part','番号'), FieldSchema('temp','温度','decimal')))
    profile = ExtractionProfile(identifier(),1,'合成配置',(PageInfo(210,297),),schema.fields,
        {'part':dict(page=1,rect=[10,20,30,8]),'temp':dict(page=1,rect=[10,40,30,8])},'page',schema.id,1)
    window.app.register_template(profile,schema)
    window.app.set_mode(sid,'page')
    rid = window.app.assign_pages(sid,[1],profile.id,1,{1:0})[0]
    select_source(window,sid)
    select_page(window,1)
    window.review_list.selection_set('temp')
    window.select_field()
    window.tabs.select(window.list_tab)
    window.root.update()
    assert window.field_id == 'temp'
    window.run_ocr()
    jobs = [window.app.job(j['id']) for j in window.app.store.rows('jobs') if j['kind']=='ocr']
    for job in jobs:
        deliver(window,job,'25' if job['data']['field_id']=='temp' else '001234')
    assert window.record['id'] == rid and window.field_id == 'temp'
    assert window.vars['value'].get() == '25'
    assert window.tabs.select() == str(window.review_tab)
    assert window.root.focus_get() == window.entries[0]
    assert not window.test_errors


@isolated_gui
def test_moving_focus_during_foreground_ocr_cancels_automatic_screen_change(window, workdir):
    _, _, records = setup(window, workdir)
    window.tabs.select(window.list_tab)
    window.root.update()
    window.run_ocr()
    job = window.app.job(window.app.latest_ocr(records[0], 'part')['id'])
    window.document_list.focus_force()
    window.root.update()
    deliver(window, job)
    assert window.tabs.select() == str(window.list_tab)
    assert window.root.focus_get() == window.document_list
    assert window.app.store.record(records[0])['data']['fields']['part']['value'] == '001234'
    assert window.ocr_review_request is None
