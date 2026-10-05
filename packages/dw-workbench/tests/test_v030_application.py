"""Cross-document assignment with synthetic bytes; no SDK, OCR engine or UI."""
from dataclasses import FrozenInstanceError, asdict, replace
import json
import pytest
from conftest import complete
from test_v020_application import source, templates, assign
from dw_workbench.domain import PageInfo, RuleError, StaleRevision, Status


TABLES = ("sources", "profiles", "records", "jobs", "events", "datasets", "artifacts",
    "schemas", "profile_schemas", "source_modes", "page_assignments", "observations", "candidates")


def snapshot(app):
    return {table: app.store.rows(table) for table in TABLES}


def test_preview_is_readonly_and_deeply_frozen_with_explicit_mode_change(app, workdir):
    sid = source(app, workdir)
    _, profiles = templates(app)
    before = snapshot(app)
    plan = app.plan_template_application(profiles[0].id, 1, {sid: [3, 1, 1, 99]})
    assert snapshot(app) == before
    assert app.mode(sid) == {"mode": None, "revision": 0}
    assert [e.page for e in plan.entries] == [1, 3, 99]
    assert [e.action for e in plan.entries] == ["apply", "apply", "skip"]
    assert plan.mode_changes[0].old_mode is None and plan.mode_changes[0].new_mode == "page"
    assert plan.mode_changes[0].expected_revision == 0
    assert plan.targets == ((sid, (1, 3, 99)),)
    with pytest.raises(FrozenInstanceError):
        plan.entries[0].action = "skip"
    with pytest.raises(FrozenInstanceError):
        plan.captured_sources[0].source.name = "changed"


def test_multiple_documents_invalid_pages_and_geometry_mismatch_have_manual_fields(app, workdir):
    first = source(app, workdir, "First.xdw")
    second = source(app, workdir, "Second.xdw", [PageInfo(210, 297), PageInfo(297, 420)])
    empty = source(app, workdir, "Empty-selection.xdw")
    _, profiles = templates(app)
    before_jobs = app.store.rows("jobs")
    plan = app.plan_template_application(profiles[0].id, 1, {first: [1, 3], second: [2, 5], empty: []})
    assert len(plan.mode_changes) == 2
    warning = next(e for e in plan.entries if e.source_id == second and e.page == 2)
    assert warning.action == "apply" and warning.geometry_matches is False and "手入力" in warning.reason
    result = app.apply_template_plan(plan)
    assert (result.applied, result.same, result.skipped, result.mode_changes) == (3, 0, 2, 2)
    assert [(app.store.record(r)["source_id"], app.store.record(r)["page"]) for r in result.record_ids] == [(first, 1), (first, 3), (second, 2)]
    assert app.mode(empty)["mode"] is None
    assert app.store.rows("jobs") == before_jobs
    record = app.store.record(result.record_ids[-1])
    assert not record["data"]["geometry_matches"]
    assert set(record["data"]["fields"]) == {"part", "temp", "note"}
    assert all(f["anchor"] is None and f["value"] == "" and f["status"] == Status.MISSING for f in record["data"]["fields"].values())
    with pytest.raises(RuleError):
        app.ocr_jobs(record["id"])


@pytest.mark.parametrize("pages", [[], [-2, 0, 99], [True, False, 1.0, "1"]])
def test_invalid_or_empty_requests_do_not_initialize_mode_or_write_any_table(app, workdir, pages):
    sid = source(app, workdir)
    _, profiles = templates(app)
    before = snapshot(app)
    plan = app.plan_template_application(profiles[0].id, 1, {sid: pages})
    assert all(e.action == "skip" for e in plan.entries)
    assert not plan.mode_changes
    result = app.apply_template_plan(plan)
    assert result.applied == result.same == result.mode_changes == 0 and not result.record_ids
    assert snapshot(app) == before


def test_default_preserves_confirmed_and_excluded_pages_even_for_same_template(app, workdir):
    sid = source(app, workdir)
    _, profiles = templates(app)
    app.set_mode(sid, "page")
    rid = assign(app, sid, [1], profiles[0])[0]
    complete(app, rid)
    app.exclude_pages(sid, [2], "表紙", {2: 0})
    before = snapshot(app)
    plan = app.plan_template_application(profiles[0].id, 1, {sid: [1, 2]})
    assert [e.current_state for e in plan.entries] == ["applied", "excluded"]
    assert all(e.action == "skip" for e in plan.entries)
    result = app.apply_template_plan(plan)
    assert (result.applied, result.same, result.skipped) == (0, 0, 2)
    assert snapshot(app) == before


def test_inclusive_same_template_is_full_noop_including_confirmations_and_running_jobs(app, workdir):
    sid = source(app, workdir)
    _, profiles = templates(app)
    app.set_mode(sid, "page")
    rid = assign(app, sid, [1], profiles[0])[0]
    complete(app, rid)
    jobs = app.ocr_jobs(rid)
    app.start_job(jobs[0])
    before = snapshot(app)
    plan = app.plan_template_application(profiles[0].id, 1, {sid: [1]}, unassigned_only=False)
    assert plan.entries[0].action == "same"
    result = app.apply_template_plan(plan)
    assert (result.applied, result.same, result.skipped, result.record_ids) == (0, 1, 0, (rid,))
    assert snapshot(app) == before


def test_inclusive_revision_change_preserves_history_dataset_candidates_and_cancels_ocr(app, workdir):
    sid = source(app, workdir)
    _, profiles = templates(app)
    newer = replace(profiles[0], version=2, name="改訂版")
    app.register_profile(newer)
    app.set_mode(sid, "page")
    old = assign(app, sid, [2], profiles[0])[0]
    complete(app, old)
    dataset = app.dataset(app.finalize(completed_only=True))
    original = app.store.record(old)["data"]
    jobs = app.ocr_jobs(old)
    app.start_job(jobs[0])
    app.finish_job(jobs[1], error="synthetic retryable failure")
    app.finish_job(jobs[2], {"source_hash": app.source(sid).sha256, "text": "old observation", "engine": {},
        "regions": [{"text": "old observation", "confidence": .9, "polygon_mm": []}]})
    candidates = app.candidates(old, "note")
    plan = app.plan_template_application(newer.id, 2, {sid: [2]}, unassigned_only=False)
    assert plan.entries[0].previous_profile_id == newer.id and plan.entries[0].previous_profile_version == 1
    result = app.apply_template_plan(plan)
    new = result.record_ids[0]
    assert result.applied == 1 and new != old
    assert not app.store.record(old)["active"] and app.store.record(old)["data"] == original
    assert [r["id"] for r in app.history_records(sid, 2)] == [new, old]
    assert app.candidates(old, "note") == candidates
    assert app.job(jobs[0])["status"] == app.job(jobs[1])["status"] == "cancelled"
    assert app.job(jobs[2])["status"] == "complete"
    app.finish_job(jobs[0], {"text": "LATE RESULT"})
    assert app.candidates(new, "part") == []
    assert all(f["value"] == "" and f["status"] == Status.MISSING for f in app.store.record(new)["data"]["fields"].values())
    assert app.dataset(dataset["id"]) == dataset


def test_inclusive_reincludes_excluded_page_with_fresh_values_and_retained_old_record(app, workdir):
    sid = source(app, workdir)
    _, profiles = templates(app)
    app.set_mode(sid, "page")
    old = assign(app, sid, [1], profiles[0])[0]
    complete(app, old)
    original = app.store.record(old)["data"]
    app.exclude_pages(sid, [1], "一時的な対象外", {1: 1})
    plan = app.plan_template_application(profiles[0].id, 1, {sid: [1]}, unassigned_only=False)
    assert plan.entries[0].current_state == "excluded" and plan.entries[0].action == "apply"
    result = app.apply_template_plan(plan)
    new = result.record_ids[0]
    assignment = app.assignments(sid)[0]
    assert assignment.state == "applied" and assignment.reason == "" and assignment.revision == 3
    assert app.store.record(old)["data"] == original and new != old
    assert app.store.record(new)["data"]["fields"]["part"]["value"] == ""


@pytest.mark.parametrize("old_mode,new_scope,target", [("document", "page", 1), ("page", "document", 0)])
def test_mode_can_change_only_on_apply_when_all_targets_unassigned(app, workdir, old_mode, new_scope, target):
    sid = source(app, workdir, pages=[PageInfo(210, 297)])
    _, profiles = templates(app)
    profile = profiles[0] if new_scope == "page" else replace(profiles[0], id="document-layout", scope="document")
    if new_scope == "document":
        app.register_profile(profile)
    app.set_mode(sid, old_mode)
    before = snapshot(app)
    plan = app.plan_template_application(profile.id, 1, {sid: [target]})
    assert snapshot(app) == before
    assert plan.mode_changes[0].old_mode == old_mode
    result = app.apply_template_plan(plan)
    assert result.mode_changes == 1 and result.applied == 1
    assert app.mode(sid) == {"mode": new_scope, "revision": 2}
    assert app.store.record(result.record_ids[0])["page"] == (target or None)


@pytest.mark.parametrize("lock", ["applied", "excluded"])
def test_scope_mismatch_with_any_assigned_or_excluded_page_skips_whole_document(app, workdir, lock):
    sid = source(app, workdir)
    _, profiles = templates(app)
    document = replace(profiles[0], id="document-layout", scope="document", pages=(PageInfo(210, 297),)*3)
    app.register_profile(document)
    app.set_mode(sid, "page")
    if lock == "applied":
        assign(app, sid, [3], profiles[0])
    else:
        app.exclude_pages(sid, [3], "表紙", {3: 0})
    before = snapshot(app)
    plan = app.plan_template_application(document.id, 1, {sid: [0]}, unassigned_only=False)
    assert plan.entries[0].action == "skip" and "処理方式" in plan.entries[0].reason
    assert not plan.mode_changes
    assert app.apply_template_plan(plan).skipped == 1
    assert snapshot(app) == before


@pytest.mark.parametrize("inclusive", [False, True])
def test_editing_even_skipped_or_same_record_invalidates_entire_plan_before_first_write(app, workdir, inclusive):
    first = source(app, workdir, "Unassigned.xdw")
    second = source(app, workdir, "Edited.xdw")
    _, profiles = templates(app)
    app.set_mode(second, "page")
    rid = assign(app, second, [1], profiles[0])[0]
    plan = app.plan_template_application(profiles[0].id, 1, {first: [1], second: [1]}, unassigned_only=not inclusive)
    assert plan.entries[-1].action == ("same" if inclusive else "skip")
    app.edit(rid, "part", 0, value="changed after preview", raw="", unit="", anchor=None)
    before = snapshot(app)
    with pytest.raises(StaleRevision):
        app.apply_template_plan(plan)
    assert snapshot(app) == before and app.mode(first)["mode"] is None


def test_change_to_unselected_assignment_invalidates_captured_document(app, workdir):
    sid = source(app, workdir)
    _, profiles = templates(app)
    app.set_mode(sid, "page")
    plan = app.plan_template_application(profiles[0].id, 1, {sid: [1]})
    app.exclude_pages(sid, [3], "変更後の除外", {3: 0})
    before = snapshot(app)
    with pytest.raises(StaleRevision):
        app.apply_template_plan(plan)
    assert snapshot(app) == before


def test_mode_aba_is_detected_even_when_current_units_and_assignments_look_same(app, workdir):
    sid = source(app, workdir)
    _, profiles = templates(app)
    app.set_mode(sid, "page")
    plan = app.plan_template_application(profiles[0].id, 1, {sid: [1]})
    app.set_mode(sid, "document", 1)
    app.set_mode(sid, "page", 2)
    before = snapshot(app)
    with pytest.raises(StaleRevision):
        app.apply_template_plan(plan)
    assert snapshot(app) == before


def test_failure_after_two_documents_written_rolls_back_records_modes_jobs_and_events(app, workdir, monkeypatch):
    first = source(app, workdir, "Existing.xdw")
    second = source(app, workdir, "New.xdw")
    _, profiles = templates(app)
    app.set_mode(first, "page")
    old = assign(app, first, [1], profiles[0])[0]
    complete(app, old)
    job = app.ocr_jobs(old)[0]
    app.start_job(job)
    plan = app.plan_template_application(profiles[1].id, 1, {first: [1], second: [2]}, unassigned_only=False)
    before = snapshot(app)
    original = app._assign_profile
    calls = []
    def fail_after_write(source, profile, assignments):
        result = original(source, profile, assignments)
        calls.append(source.id)
        if len(calls) == 2:
            raise OSError("synthetic save failure after writes")
        return result
    monkeypatch.setattr(app, "_assign_profile", fail_after_write)
    with pytest.raises(OSError):
        app.apply_template_plan(plan)
    assert snapshot(app) == before
    assert app.job(job)["status"] == "running" and app.store.record(old)["active"]
    monkeypatch.setattr(app, "_assign_profile", original)
    assert app.apply_template_plan(plan).applied == 2


@pytest.mark.parametrize("change", ["action", "entry", "duplicate", "mode", "fingerprint", "target-order", "target-duplicate", "capture", "condition"])
def test_altered_preview_cannot_change_approved_operation(app, workdir, change):
    sid = source(app, workdir)
    _, profiles = templates(app)
    plan = app.plan_template_application(profiles[0].id, 1, {sid: [1, 2]})
    mutations = {
        "action": lambda: replace(plan, entries=(replace(plan.entries[0], action="skip"), plan.entries[1])),
        "entry": lambda: replace(plan, entries=plan.entries[1:]),
        "duplicate": lambda: replace(plan, entries=plan.entries+(plan.entries[0],)),
        "mode": lambda: replace(plan, mode_changes=()),
        "fingerprint": lambda: replace(plan, profile_fingerprint="0"*64),
        "target-order": lambda: replace(plan, targets=((sid, (2, 1)),)),
        "target-duplicate": lambda: replace(plan, targets=((sid, (1, 1, 2)),)),
        "capture": lambda: replace(plan, captured_sources=()),
        "condition": lambda: replace(plan, unassigned_only="yes"),
    }
    before = snapshot(app)
    with pytest.raises(RuleError):
        app.apply_template_plan(mutations[change]())
    assert snapshot(app) == before


def test_corrupt_assignment_reference_is_rejected_during_preview_without_repair(app, workdir):
    sid = source(app, workdir)
    _, profiles = templates(app)
    app.set_mode(sid, "page")
    first, second = assign(app, sid, [1, 2], profiles[0])
    app.store.db.execute("UPDATE page_assignments SET current_record_id=? WHERE source_id=? AND page=1", (second, sid))
    before = snapshot(app)
    with pytest.raises(RuleError):
        app.plan_template_application(profiles[0].id, 1, {sid: [1]}, unassigned_only=False)
    assert snapshot(app) == before


def test_corrupt_source_snapshot_identity_cannot_claim_an_application_succeeded(app, workdir):
    sid = source(app, workdir)
    _, profiles = templates(app)
    app.store.db.execute("INSERT INTO sources VALUES(?,?)", ("row-only-id", json.dumps(asdict(app.source(sid)))))
    before = snapshot(app)
    with pytest.raises(RuleError):
        app.plan_template_application(profiles[0].id, 1, {"row-only-id": [1]})
    assert snapshot(app) == before


@pytest.mark.parametrize("change", ["targets-none", "short-pair", "source-list", "page-bool", "source-duplicate", "profile-list", "version-list"])
def test_malformed_inmemory_plan_is_rejected_as_business_error_before_database_access(app, workdir, change):
    sid = source(app, workdir)
    _, profiles = templates(app)
    plan = app.plan_template_application(profiles[0].id, 1, {sid: [1]})
    mutations = {
        "targets-none": lambda: replace(plan, targets=None),
        "short-pair": lambda: replace(plan, targets=((sid,),)),
        "source-list": lambda: replace(plan, targets=(([1], (1,)),)),
        "page-bool": lambda: replace(plan, targets=((sid, (True,)),)),
        "source-duplicate": lambda: replace(plan, targets=plan.targets+plan.targets),
        "profile-list": lambda: replace(plan, profile_id=[]),
        "version-list": lambda: replace(plan, profile_version=[]),
    }
    before = snapshot(app)
    with pytest.raises(RuleError):
        app.apply_template_plan(mutations[change]())
    assert snapshot(app) == before


def test_document_profiles_apply_one_record_per_source_and_report_actual_geometry(app, workdir):
    first = source(app, workdir, "First.xdw", [PageInfo(210, 297)]*3)
    second = source(app, workdir, "Second.xdw", [PageInfo(210, 297)])
    _, profiles = templates(app)
    document = replace(profiles[0], id="document-layout", scope="document", pages=(PageInfo(210, 297),)*3)
    app.register_profile(document)
    plan = app.plan_template_application(document.id, 1, {first: [0, 1], second: [0]})
    assert [e.geometry_matches for e in plan.entries] == [True, None, False]
    result = app.apply_template_plan(plan)
    assert result.applied == 2 and result.skipped == 1
    assert all(app.store.record(r)["page"] is None for r in result.record_ids)
    assert all(app.mode(s)["mode"] == "document" for s in (first, second))
