"""Application behavior with deliberately synthetic, non-SDK document bytes."""
from dataclasses import asdict, replace
import json
import pytest
from conftest import complete
from dw_workbench.application import Workbench
from dw_workbench.domain import (Anchor, ExtractionProfile, FieldSchema, PageInfo, ResultSchema,
    RuleError, StaleRevision, Status, identifier, state_from)
from dw_workbench.library import TemplateLibrary


def source(app, root, name="Synthetic.xdw", pages=None):
    path = root/name
    path.write_bytes(b"Synthetic unit-test document, NOT a valid SDK XDW")
    id = app.prepare_source(path)
    app.finish_job("inspect-"+id, {"pages": [asdict(p) for p in (pages or [PageInfo(210, 297)]*3)]})
    return id


def templates(app):
    schema = ResultSchema(identifier(), 1, "測定項目", (FieldSchema("part", "部品番号"),
        FieldSchema("temp", "温度", "decimal", True, "℃"), FieldSchema("note", "備考", required=False)))
    app.register_schema(schema)
    profiles = []
    for index in range(2):
        p = ExtractionProfile(identifier(), 1, "配置"+str(index), (PageInfo(210, 297),), schema.fields,
            {f.id: {"page": 1, "rect": [10+50*index, 20+20*j, 30, 8]} for j, f in enumerate(schema.fields)},
            "page", schema.id, schema.version)
        app.register_profile(p)
        profiles.append(p)
    return schema, profiles


def assign(app, sid, pages, p):
    expected = {a.page: a.revision for a in app.assignments(sid)}
    return app.assign_pages(sid, pages, p.id, p.version, expected)


def test_pages_are_independent_and_actual_anchor_pages_are_frozen(app, workdir):
    sid = source(app, workdir)
    _, ps = templates(app)
    app.set_mode(sid, "page")
    first, second = assign(app, sid, [1, 2], ps[0])
    complete(app, first)
    complete(app, second)
    r = app.store.record(second)
    s = state_from(r["data"]["fields"]["part"])
    app.edit(second, "part", r["revision"], value="001235", raw="001235", unit="", anchor=s.anchor)
    app.accept(second, "part", app.store.record(second)["revision"])
    assert app.store.record(first)["data"]["fields"]["part"]["value"] == "001234"
    assert s.anchor.page == 2
    assert [x["page"] for x in app.incomplete()] == [3]
    jobs = app.ocr_jobs(second)
    assert all(app.job(j)["data"]["page"] == 2 for j in jobs)
    assert len([j for j in app.pending_jobs() if j["kind"] == "render"]) == 1
    app.exclude_pages(sid, [3], "説明ページ", {3: 0})
    dataset = app.dataset(app.finalize())
    assert dataset["format_version"] == 2
    assert [r["page"] for r in dataset["groups"][0]["records"]] == [1, 2]
    assert dataset["excluded"][0]["page"] == 3 and dataset["excluded"][0]["reason"] == "説明ページ"


def test_same_assignment_is_noop_but_stale_requests_are_rejected(app, workdir):
    sid = source(app, workdir)
    _, ps = templates(app)
    app.set_mode(sid, "page")
    rid = assign(app, sid, [1], ps[0])[0]
    complete(app, rid)
    before = app.store.record(rid)
    assert assign(app, sid, [1], ps[0]) == [rid]
    assert app.store.record(rid) == before
    with pytest.raises(StaleRevision):
        app.assign_pages(sid, [1], ps[0].id, 1, {1: 0})
    with pytest.raises(RuleError):
        app.set_mode(sid, "document", app.mode(sid)["revision"])


def test_template_change_preserves_unexported_history_and_cancels_late_ocr(app, workdir):
    sid = source(app, workdir)
    _, ps = templates(app)
    app.set_mode(sid, "page")
    old = assign(app, sid, [2], ps[0])[0]
    complete(app, old)
    before = app.store.record(old)["data"]
    job = app.ocr_jobs(old)[0]
    app.start_job(job)
    new = assign(app, sid, [2], ps[1])[0]
    app.finish_job(job, {"text": "LATE", "regions": [{"text": "LATE"}], "engine": {}})
    assert app.job(job)["status"] == "cancelled"
    assert app.candidates(new, "part") == []
    assert app.store.record(old)["data"] == before
    assert app.store.record(new)["data"]["fields"]["part"]["value"] == ""
    assert app.store.record(new)["data"]["fields"]["part"]["status"] == Status.MISSING
    assert [r["id"] for r in app.history_records(sid, 2)] == [new, old]
    with pytest.raises(RuleError):
        complete(app, old)
    assert not any(app.job(j["id"])["data"].get("record_id") == old for j in app.pending_jobs())


def test_bulk_invalid_target_is_atomic_and_manual_anchor_cannot_cross_page(app, workdir):
    sid = source(app, workdir)
    _, ps = templates(app)
    app.set_mode(sid, "page")
    before = app.assignments(sid)
    with pytest.raises(RuleError):
        app.assign_pages(sid, [1, 99], ps[0].id, 1, {1: 0, 99: 0})
    assert app.assignments(sid) == before and app.store.rows("records") == []
    rid = assign(app, sid, [1], ps[0])[0]
    original = app.source(sid)
    wrong = Anchor(sid, original.sha256, 2, (10, 20, 30, 8))
    with pytest.raises(RuleError):
        app.edit(rid, "part", 0, value="001234", raw="001234", unit="", anchor=wrong)


def test_mismatched_page_still_can_be_completed_manually(app, workdir):
    sid = source(app, workdir, pages=[PageInfo(210, 297), PageInfo(297, 420)])
    _, ps = templates(app)
    app.set_mode(sid, "page")
    rid = assign(app, sid, [2], ps[0])[0]
    r = app.store.record(rid)
    assert not r["data"]["geometry_matches"]
    assert set(r["data"]["fields"]) == {"part", "temp", "note"}
    with pytest.raises(RuleError):
        app.ocr_jobs(rid)
    for field, value in (("part", "001234"), ("temp", "25.0")):
        r = app.store.record(rid)
        app.edit(rid, field, r["revision"], value=value, raw=value, unit=r["data"]["fields"][field]["unit"],
            anchor=Anchor(sid, app.source(sid).sha256, 2, (10, 20, 30, 8)))
        app.accept(rid, field, app.store.record(rid)["revision"])
    app.mark(rid, "note", app.store.record(rid)["revision"], Status.NOT_APPLICABLE, "記載なし")
    app.exclude_pages(sid, [1], "対象外の表紙", {1: 0})
    assert app.dataset(app.finalize())["groups"][0]["records"][0]["page"] == 2


def test_shared_schema_groups_different_layouts_and_document_mode(app, workdir):
    schema, ps = templates(app)
    sid = source(app, workdir, pages=[PageInfo(210, 297)]*2)
    app.set_mode(sid, "page")
    for page, p in enumerate(ps, 1):
        complete(app, assign(app, sid, [page], p)[0])
    doc = source(app, workdir, "Document.xdw", [PageInfo(210, 297)])
    profile = replace(ps[0], id=identifier(), scope="document", name="文書用")
    app.register_profile(profile)
    complete(app, app.apply_profile(doc, profile.id, 1))
    frozen = app.dataset(app.finalize())
    assert len(frozen["groups"]) == 1
    assert frozen["groups"][0]["schema"]["id"] == schema.id
    assert [r["page"] for r in frozen["groups"][0]["records"]] == [1, 2, None]
    assert len({r["profile"]["id"] for r in frozen["groups"][0]["records"]}) == 3
    # Same displayed names do not imply semantic identity.
    separate = ResultSchema(identifier(), 1, schema.name, schema.fields)
    app.register_schema(separate)
    p = replace(ps[0], id=identifier(), schema_id=separate.id)
    app.register_profile(p)
    extra = source(app, workdir, "Separate.xdw", [PageInfo(210, 297)])
    app.set_mode(extra, "page")
    complete(app, assign(app, extra, [1], p)[0])
    assert len(app.dataset(app.finalize())["groups"]) == 2
    assert len(frozen["groups"]) == 1


def test_project_import_is_independent_of_library_and_idempotent(app, workdir):
    _, ps = templates(app)
    library = TemplateLibrary(workdir/"Portable")
    other = Workbench(workdir/"別案件")
    try:
        app.publish_template(library, ps[0].id, 1)
        imported = other.import_template(library, ps[0].id, 1)
        assert other.import_template(library, ps[0].id, 1) == imported
        library.close()
        assert other.profile(ps[0].id, 1) == imported
        assert len(other.schemas()) == 1
        other.store.backup(workdir/"復元案件")
    finally:
        library.close()
        other.close()
    restored = Workbench(workdir/"復元案件")
    try:
        assert restored.profile(ps[0].id, 1) == imported
    finally:
        restored.close()


def test_atomic_authoring_reuses_schema_and_does_not_save_partial_definition(app):
    fields = (FieldSchema("part", "部品番号"),)
    schema = ResultSchema(identifier(), 1, "部品", fields)
    profile = ExtractionProfile(identifier(), 1, "位置A", (PageInfo(210, 297),), fields,
        {"part": {"page": 1, "rect": [10, 20, 30, 8]}}, "page", schema.id, 1)
    app.register_template(profile, schema)
    alternative = replace(profile, id=identifier(), name="位置B", regions={"part": {"page": 1, "rect": [60, 20, 30, 8]}})
    app.register_template(alternative, schema)
    app.register_template(replace(profile, version=2), schema)
    assert len(app.schemas()) == 1 and len(app.profiles()) == 3
    orphan = replace(schema, id=identifier(), name="未登録の定義")
    with pytest.raises(StaleRevision):
        app.register_template(replace(profile, schema_id=orphan.id), orphan)
    assert len(app.schemas()) == 1
