"""Machine prefill is pending and may never replace human ownership/evidence."""
from dataclasses import asdict, replace
import json
import pytest
from dw_workbench.application import Workbench
from dw_workbench.domain import Anchor, Status, identifier
from dw_workbench.storage import encode


def result(text='001234', rows=None, **extra):
    return dict(text=text, regions=rows if rows is not None else [dict(text=text, confidence=.98,
        polygon_mm=[[10, 20], [40, 20], [40, 28], [10, 28]])], engine={'name': 'synthetic OCR'}, **extra)


def finish(app, job, text='001234', **extra):
    app.finish_job(job, result(text, **extra))
    return json.loads(app.job(job)['result'])['prefill']


def edit(app, rid, fid, value='', **extra):
    state = app.store.record(rid)['data']['fields'][fid]
    changes = dict(value=value, raw=value, unit=state['unit'], anchor=Anchor(**state['anchor']) if state['anchor'] else None)
    changes.update(extra)
    app.edit(rid, fid, app.store.record(rid)['revision'], **changes)


def test_prefill_retains_exact_text_and_mm_anchor_but_not_confirmation(app, sample):
    _, _, rid = sample
    before = app.store.record(rid)
    job = app.ocr_jobs(rid)[0]
    assert finish(app, job)['status'] == 'applied'
    after = app.store.record(rid)
    state = after['data']['fields']['part']
    assert state['value'] == state['raw'] == '001234'
    assert state['anchor'] == before['data']['fields']['part']['anchor']
    assert state['status'] == Status.PENDING and state['accepted_revision'] is None
    assert state['candidate_id'] == job and app.input_origin(rid, 'part') == 'ocr'
    assert after['revision'] == before['revision']+1
    assert app.next_unfinished()['field_id'] == 'part'


@pytest.mark.parametrize('action', ['empty', 'raw', 'unit', 'anchor', 'deferred', 'adopted', 'accepted'])
def test_human_changes_and_explicit_empty_are_never_overwritten(app, sample, action):
    sid, _, rid = sample
    jobs = app.ocr_jobs(rid)
    if action == 'empty':
        edit(app, rid, 'part', '')  # Same initial bytes still express human intent.
    elif action in ('raw', 'unit'):
        edit(app, rid, 'part', '', **{action: 'human'})
    elif action == 'anchor':
        edit(app, rid, 'part', '', anchor=Anchor(sid, app.source(sid).sha256, 1, (11, 22, 20, 8)))
    elif action == 'deferred':
        app.mark(rid, 'part', 0, Status.DEFERRED, '原文再確認')
    else:
        finish(app, jobs[0])
        if action == 'adopted':
            app.adopt(rid, jobs[0], app.store.record(rid)['revision'])
        else:
            app.accept(rid, 'part', app.store.record(rid)['revision'])
        jobs = app.ocr_jobs(rid)
    before = app.store.record(rid)
    assert finish(app, jobs[0], '999999')['status'] == 'protected'
    assert app.store.record(rid) == before
    assert app.input_origin(rid, 'part') == 'human'
    assert finish(app, jobs[1], '２５.０')['status'] == 'applied'  # Independent untouched field.
    assert app.store.record(rid)['data']['fields']['part'] == before['data']['fields']['part']


def test_prefilled_values_are_not_replaced_and_numeric_validation_waits_for_human(app, sample):
    _, _, rid = sample
    first = app.ocr_jobs(rid)
    finish(app, first[0], '000125')
    finish(app, first[1], '２５.０')
    state = app.store.record(rid)['data']['fields']['temp']
    assert state['value'] == state['raw'] == '２５.０' and state['unit'] == '℃'
    assert state['status'] == Status.PENDING
    before = app.store.record(rid)
    second = app.ocr_jobs(rid)
    assert finish(app, second[0], '999999')['status'] == 'protected'
    assert app.store.record(rid) == before
    app.accept(rid, 'temp', before['revision'])
    state = app.store.record(rid)['data']['fields']['temp']
    assert state['value'] == '25.0' and state['raw'] == '２５.０'
    assert state['status'] == Status.ACCEPTED


@pytest.mark.parametrize('text,extra', [
    ('', {'rows': []}), ('25℃', {}), ('NaN', {}),
    ('25', {'alternatives': ['25', '26']}),
    ('25', {'rows': [dict(text='26', confidence=.99, polygon_mm=[])]}),
])
def test_empty_invalid_numeric_or_ambiguous_results_require_review(app, sample, text, extra):
    _, _, rid = sample
    before = app.store.record(rid)
    outcome = finish(app, app.ocr_jobs(rid)[1], text, **extra)
    assert outcome['status'] == 'needs_review' and outcome['reason']
    assert app.store.record(rid) == before


def test_multiple_lines_form_one_candidate_and_history_does_not_block_new_input(app, sample):
    _, _, rid = sample
    old = app.ocr_jobs(rid)[0]
    legacy = dict(app.job(old)['data'])
    legacy.pop('prefill_allowed')
    app.store.db.execute('UPDATE jobs SET data=? WHERE id=?', (encode(legacy), old))
    assert finish(app, old, '古い履歴')['status'] == 'protected'
    assert app.store.record(rid)['revision'] == 0
    current = app.ocr_jobs(rid)[0]
    rows = [dict(text=text, confidence=.98, polygon_mm=[]) for text in ('部品', '001234')]
    assert finish(app, current, '部品 001234', rows=rows)['status'] == 'applied'
    assert len(app.candidates(rid, 'part')) == 2
    assert app.store.record(rid)['data']['fields']['part']['value'] == '部品 001234'


def test_old_async_results_are_history_only_and_changed_assignment_cancels(app, sample):
    sid, profile, rid = sample
    older = app.ocr_jobs(rid)[0]
    app.start_job(older)
    newer = app.ocr_jobs(rid)[0]
    assert finish(app, older, 'OLD')['status'] == 'superseded'
    assert finish(app, newer, 'NEW')['status'] == 'applied'
    late = app.ocr_jobs(rid)[1]
    app.start_job(late)
    revised = replace(profile, id=identifier())
    app.register_profile(revised)
    replacement = app.assign_pages(sid, [0], revised.id, 1, {0: app.assignments(sid)[0].revision})[0]
    app.finish_job(late, result('LATE'))
    assert app.job(late)['status'] == 'cancelled'
    assert not app.candidates(replacement, 'temp')
    assert app.store.record(replacement)['data']['fields']['part']['value'] == ''


def test_failed_retry_restart_and_legacy_conservative_ownership(app, sample):
    _, _, rid = sample
    job = app.ocr_jobs(rid)[0]
    app.finish_job(job, error='synthetic failure')
    before = app.store.record(rid)
    assert before['revision'] == 0
    root = app.store.root
    app.close()
    reopened = Workbench(root)
    try:
        assert finish(reopened, job)['status'] == 'applied'
        assert reopened.store.record(rid)['data']['fields']['part']['status'] == Status.PENDING
        edit(reopened, rid, 'part', '')
        cleared = reopened.store.record(rid)
        retry = reopened.ocr_jobs(rid)[0]
        assert finish(reopened, retry, 'UNWANTED')['status'] == 'protected'
        assert reopened.store.record(rid) == cleared
        data = dict(cleared['data'])
        data.pop('input_tracking')
        reopened.store.db.execute('UPDATE records SET data=? WHERE id=?', (encode(data), rid))
        assert reopened.input_origin(rid, 'part') == 'unknown'
        assert finish(reopened, reopened.ocr_jobs(rid)[1], '99')['status'] == 'protected'
    finally:
        reopened.close()


def test_legacy_untouched_revision_zero_can_prefill_without_migration(app, sample):
    _, _, rid = sample
    record = app.store.record(rid)
    record['data'].pop('input_tracking')
    app.store.db.execute('UPDATE records SET data=? WHERE id=?', (encode(record['data']), rid))
    assert app.store.db.execute('PRAGMA user_version').fetchone()[0] == 2
    assert finish(app, app.ocr_jobs(rid)[0])['status'] == 'applied'
    assert app.store.db.execute('PRAGMA user_version').fetchone()[0] == 2
