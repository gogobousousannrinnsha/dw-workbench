"""Independent behavior audit for page identity, transactional changes and isolated restores."""
from dataclasses import asdict, replace
import json
import shutil

import pytest

from dw_workbench.application import Workbench
from dw_workbench.domain import Anchor, ExtractionProfile, FieldSchema, PageInfo, ResultSchema, RuleError, StaleRevision, state_from
from dw_workbench.library import TemplateLibrary
from dw_workbench.storage import digest, encode


@pytest.fixture
def audit_source(app, workdir):
    path = workdir / "Audit 3ページ.xdw"
    path.write_bytes(b"Three-page behavior fixture, not an SDK-valid XDW")
    source_id = app.prepare_source(path)
    app.finish_job("inspect-" + source_id, {"pages": [asdict(PageInfo(210, 297))] * 3})
    app.set_mode(source_id, "page")
    return source_id


def make_profile(app, id="layout-a", version=1, scope="page"):
    schema_id = "audit-schema"
    if not app.schemas():
        app.register_schema(ResultSchema(schema_id, 1, "監査用項目", (FieldSchema("part", "部品番号"),)))
    schema = app.schema(schema_id, 1)
    profile = ExtractionProfile(id, version, "監査帳票 " + id, (PageInfo(210, 297),), schema.fields,
        {"part": {"page": 1, "rect": [10 + version, 20, 40, 10]}}, scope, schema.id, schema.version)
    app.register_profile(profile)
    return profile


def assign(app, source_id, profile, pages):
    revisions = {a.page: a.revision for a in app.assignments(source_id)}
    return app.assign_pages(source_id, pages, profile.id, profile.version, revisions)


def complete_record(app, id, value="00123"):
    record = app.store.record(id)
    state = state_from(record["data"]["fields"]["part"])
    app.edit(id, "part", record["revision"], value=value, unit="", raw=value, anchor=state.anchor)
    app.accept(id, "part", app.store.record(id)["revision"])


def result(text="OCR候補"):
    return {"regions": [{"text": text, "confidence": .9, "polygon_mm": [[11, 20], [40, 20], [40, 30], [11, 30]]}],
        "text": text, "engine": {"id": "independent-audit"}}


def test_batch_stale_second_target_changes_nothing(app, audit_source):
    p1 = make_profile(app)
    p2 = make_profile(app, "layout-b")
    old = assign(app, audit_source, p1, [1, 2])
    complete_record(app, old[0], "accepted-page1")
    pending = app.ocr_jobs(old[0])[0]
    records_before = app.store.rows("records")
    assignments_before = app.assignments(audit_source)
    events_before = app.store.rows("events")
    with pytest.raises(StaleRevision):
        app.assign_pages(audit_source, [1, 2], p2.id, 1, {1: 1, 2: 0})
    assert app.store.rows("records") == records_before
    assert app.assignments(audit_source) == assignments_before
    assert app.store.rows("events") == events_before
    assert app.job(pending)["status"] == "pending"


def test_same_template_noop_still_checks_expected_revision(app, audit_source):
    p = make_profile(app)
    record = assign(app, audit_source, p, [1])[0]
    complete_record(app, record)
    before = app.store.record(record)
    events = app.store.rows("events")
    with pytest.raises(StaleRevision):
        app.assign_pages(audit_source, [1], p.id, 1, {1: 0})
    assert app.assign_pages(audit_source, [1], p.id, 1, {1: 1}) == [record]
    assert app.store.record(record) == before
    assert app.store.rows("events") == events


def test_mode_can_change_before_assignment_and_locks_after_exclusion(app, audit_source):
    current = app.mode(audit_source)
    changed = app.set_mode(audit_source, "document", current["revision"])
    assert [a.page for a in app.assignments(audit_source)] == [0]
    changed = app.set_mode(audit_source, "page", changed["revision"])
    assert [a.page for a in app.assignments(audit_source)] == [1, 2, 3]
    app.exclude_pages(audit_source, [2], "説明ページ", {2: 0})
    with pytest.raises(RuleError, match="変更できません"):
        app.set_mode(audit_source, "document", changed["revision"])
    with pytest.raises(StaleRevision):
        app.exclude_pages(audit_source, [1, 3], "説明", {1: 0, 3: 1})
    assert app.assignments(audit_source)[0].state == "unassigned"


def test_manual_anchor_must_stay_on_record_page(app, audit_source):
    p = make_profile(app)
    record = assign(app, audit_source, p, [2])[0]
    source = app.source(audit_source)
    before = app.store.record(record)
    with pytest.raises(RuleError, match="対象ページ"):
        app.edit(record, "part", 0, value="00123", unit="", raw="00123",
            anchor=Anchor(source.id, source.sha256, 1, (11, 20, 40, 10)))
    assert app.store.record(record) == before


def test_late_success_and_failure_never_touch_replacement(app, audit_source):
    p1, p2 = make_profile(app), make_profile(app, "layout-b")
    old = assign(app, audit_source, p1, [1])[0]
    jobs = app.ocr_jobs(old) + app.ocr_jobs(old)
    for job in jobs:
        app.start_job(job)
    new = assign(app, audit_source, p2, [1])[0]
    complete_record(app, new, "new confirmed value")
    before = app.store.record(new)
    app.finish_job(jobs[0], result())
    app.finish_job(jobs[1], error="late worker failure")
    assert app.store.record(new) == before
    assert app.candidates(new, "part") == []
    assert all(app.job(job)["status"] == "cancelled" for job in jobs)
    assert app.start_job(jobs[0]) is None
    with pytest.raises(RuleError, match="閲覧専用"):
        app.ocr_jobs(old)
    with pytest.raises(RuleError):
        app.edit(old, "part", 0, value="mutate history", unit="", raw="", anchor=None)


def test_manual_edit_during_ocr_does_not_cancel_same_assignment(app, audit_source):
    p = make_profile(app)
    record = assign(app, audit_source, p, [3])[0]
    job = app.ocr_jobs(record)[0]
    app.start_job(job)
    complete_record(app, record, "human confirmed")
    before = app.store.record(record)
    app.finish_job(job, result("machine different"))
    assert app.job(job)["status"] == "complete"
    assert app.store.record(record) == before
    candidate = app.candidates(record, "part")[0]
    assert candidate["anchor"]["page"] == 3 and candidate["text"] == "machine different"


def test_archived_confirmed_value_never_enters_new_finalization(app, audit_source):
    p1 = make_profile(app)
    old = assign(app, audit_source, p1, [1])[0]
    complete_record(app, old, "old accepted")
    p2 = make_profile(app, "layout-b")
    new = assign(app, audit_source, p2, [1])[0]
    complete_record(app, new, "current accepted")
    app.exclude_pages(audit_source, [2, 3], "説明ページ", {2: 0, 3: 0})
    id = app.finalize()
    frozen = app.dataset(id)
    assert [r["id"] for g in frozen["groups"] for r in g["records"]] == [new]
    assert frozen["groups"][0]["records"][0]["fields"]["part"]["value"] == "current accepted"
    assert [(r["id"], r["active"]) for r in app.history_records(audit_source, 1)] == [(new, 1), (old, 0)]
    complete_record(app, new, "changed later")
    assert app.dataset(id) == frozen


def test_tampered_assignment_cannot_be_finalized(app, audit_source):
    p = make_profile(app)
    first, second = assign(app, audit_source, p, [1, 2])
    complete_record(app, first, "one")
    complete_record(app, second, "two")
    app.exclude_pages(audit_source, [3], "説明", {3: 0})
    app.store.db.execute("UPDATE page_assignments SET current_record_id=? WHERE source_id=? AND page=1", (second, audit_source))
    with pytest.raises(RuleError, match="割当"):
        app.finalize()
    assert app.store.rows("datasets") == []


def test_backup_restore_has_no_common_catalog_dependency(app, audit_source, workdir):
    p = make_profile(app)
    catalog_root = workdir / "common portable"
    library = TemplateLibrary(catalog_root)
    app.publish_template(library, p.id, p.version)
    imported = Workbench(workdir / "other project")
    try:
        imported.import_template(library, p.id, p.version)
        imported.import_template(library, p.id, p.version)
        assert len(imported.profiles()) == 1
        imported.store.backup(workdir / "independent backup")
    finally:
        imported.close()
        library.close()
    shutil.rmtree(catalog_root)
    restored = Workbench(workdir / "independent backup")
    try:
        assert restored.profile(p.id, 1) == p
        assert restored.schema(p.schema_id, 1).fields == p.fields
        assert restored.store.verify()
    finally:
        restored.close()


def test_corrupted_ocr_job_cannot_bind_candidate_to_other_page(app, audit_source):
    p = make_profile(app)
    record = assign(app, audit_source, p, [2])[0]
    job = app.ocr_jobs(record)[0]
    data = app.job(job)["data"]
    data["page"] = 1
    app.store.db.execute("UPDATE jobs SET data=? WHERE id=?", (encode(data), job))
    # Stored job coordinates must be rechecked before any machine result is adopted as a candidate.
    started = app.start_job(job)
    if started is not None:
        with pytest.raises(RuleError):
            app.finish_job(job, result())
    assert app.candidates(record, "part") == []


def test_backup_of_tampered_fixed_source_stays_incomplete(app, audit_source, workdir):
    source = app.source(audit_source)
    app.store.path(source.path).write_bytes(b"tampered fixed original")
    target = workdir / "must remain incomplete"
    with pytest.raises(RuleError, match="ハッシュ"):
        app.store.backup(target)
    assert (target / "INCOMPLETE.txt").exists()
    with pytest.raises(RuleError, match="未完了"):
        Workbench(target)


def test_restored_pending_ocr_requeues_missing_completed_render(app, audit_source, workdir):
    p = make_profile(app)
    record = assign(app, audit_source, p, [2])[0]
    ocr_job = app.ocr_jobs(record)[0]
    render_id = f"render-{audit_source}-2-300"
    image = app.store.path(app.job(render_id)["data"]["image"])
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"Synthetic cache image, no image decoding needed")
    app.finish_job(render_id, {"image_sha256": digest(image)})
    app.start_job(ocr_job)
    backup = workdir / "Pending OCR restored without cache"
    app.store.backup(backup)
    restored = Workbench(backup)
    try:
        assert not restored.store.path(restored.job(render_id)["data"]["image"]).exists()
        pending = restored.pending_jobs()
        assert [job["id"] for job in pending] == [render_id, ocr_job]
        assert restored.job(render_id)["status"] == "pending"
        assert restored.job(ocr_job)["status"] == "pending"
    finally:
        restored.close()
