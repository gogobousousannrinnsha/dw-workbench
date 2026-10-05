from conftest import complete
from test_v020_application import source, templates, assign
from dw_workbench.application import Workbench
from dw_workbench.domain import Status


def test_navigation_order_wrap_exclusions_history_and_reopen(app, workdir):
    first = source(app, workdir, name='first.xdw')
    second = source(app, workdir, name='second.xdw')
    _, profiles = templates(app)
    app.set_mode(first, 'page')
    app.set_mode(second, 'page')
    r1, r2 = assign(app, first, [1, 2], profiles[0])
    r3 = assign(app, second, [1], profiles[0])[0]
    complete(app, r1)
    app.mark(r2, 'part', app.store.record(r2)['revision'], Status.DEFERRED, '後で確認')
    app.exclude_pages(first, [3], '表紙', {3: 0})
    queue = app.review_targets()
    assert [(t['source_id'], t['page'], t['field_id']) for t in queue[:6]] == [
        (first, page, field) for page in (1, 2) for field in ('part', 'temp', 'note')]
    assert app.next_unfinished((first, 1, 'part'))['record_id'] == r2
    assert app.next_unfinished((first, 2, 'part'))['field_id'] == 'temp'
    assert app.next_unfinished((first, 2, 'note'))['record_id'] == r3
    assert app.next_unfinished((second, 1, 'note'))['page'] == 2  # unassigned
    assert app.next_unfinished((second, 3, None))['record_id'] == r2  # wraps
    old = app.store.record(r2)
    newer = assign(app, first, [2], profiles[1])[0]
    assert all(t['record_id'] != r2 for t in app.review_targets())
    assert app.store.record(r2) == old | {'active': 0}
    expected = app.review_targets()
    root = app.store.root
    app.close()
    reopened = Workbench(root)
    try:
        assert reopened.review_targets() == expected
        assert reopened.next_unfinished()['record_id'] == newer
    finally:
        reopened.close()


def test_all_complete_and_unfinished_registration(app, sample, workdir):
    _, _, record = sample
    complete(app, record)
    assert app.next_unfinished() is None
    path = workdir/'import.xdw'
    path.write_bytes(b'synthetic unfinished import')
    sid = app.prepare_source(path)
    target = app.next_unfinished()
    assert target['source_id'] == sid and target['job_id'] == 'inspect-'+sid
