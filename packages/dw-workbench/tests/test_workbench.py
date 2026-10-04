from dataclasses import asdict, replace
from decimal import Decimal
import csv
import json
import os
import sqlite3
import pytest
from dw_workbench.domain import (Anchor, ExtractionProfile, FieldSchema, PageInfo, RuleError, StaleRevision,
    Status, crop_box, pixel_to_mm, state_from)
from dw_workbench.storage import FileLock, digest
from dw_workbench.application import Workbench
from dw_workbench.exporting import excel_number
from conftest import complete


def test_independent_same_spelling_and_reconfirmation(app, sample):
    _, _, record = sample
    complete(app, record)
    r = app.store.record(record)
    temp = state_from(r["data"]["fields"]["temp"])
    app.edit(record, "temp", r["revision"], value="001234", raw="001234", unit=temp.unit, anchor=temp.anchor)
    r = app.store.record(record)
    assert r["data"]["fields"]["part"]["value"] == r["data"]["fields"]["temp"]["value"]
    part = state_from(r["data"]["fields"]["part"])
    app.edit(record, "part", r["revision"], value="001235", raw="001234", unit="", anchor=part.anchor)
    r = app.store.record(record)
    assert r["data"]["fields"]["temp"]["value"] == "001234"
    assert r["data"]["fields"]["part"]["status"] == Status.PENDING


def test_revision_rollback_and_pragmas(app, sample):
    _, _, record = sample
    complete(app, record)
    r = app.store.record(record)
    s = state_from(r["data"]["fields"]["part"])
    with pytest.raises(StaleRevision):
        app.edit(record, "part", 0, value="lost", unit="", raw="", anchor=s.anchor)
    assert app.store.record(record) == r
    assert app.store.db.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    assert app.store.db.execute("PRAGMA synchronous").fetchone()[0] == 2
    assert app.store.db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with pytest.raises(RuntimeError):
        with app.store.transaction():
            app.store.update(record, r["revision"], {"bad": True})
            raise RuntimeError("abort")
    assert app.store.record(record) == r


def test_confirmation_requires_value_and_anchor(app, sample):
    _, _, record = sample
    with pytest.raises(RuleError):
        app.accept(record, "part", 0)
    app.edit(record, "part", 0, value="abc", unit="", raw="abc", anchor=None)
    with pytest.raises(RuleError):
        app.accept(record, "part", 1)
    with pytest.raises(RuleError):
        app.mark(record, "part", 1, Status.NOT_APPLICABLE, "不要")
    with pytest.raises(RuleError):
        app.mark(record, "note", 1, Status.NOT_APPLICABLE, "")


@pytest.mark.parametrize("value,expected", [("００１.２５０", "1.250"), ("-0.00", "-0.00"), ("1e-3", "0.001")])
def test_decimal_and_fullwidth(value, expected):
    assert FieldSchema("x", "x", "decimal").canonical(value) == expected


@pytest.mark.parametrize("value", ["NaN", "Infinity", "", "25℃", "1,234"])
def test_invalid_decimal(value):
    with pytest.raises(RuleError):
        FieldSchema("x", "x", "decimal").canonical(value)


@pytest.mark.parametrize("value,numeric", [("123456789012345", True), ("1234567890123456", False), ("0.123456789012345", True), ("0.1234567890123456", False), ("1e309", False), ("1e-309", False), ("25.0", True)])
def test_excel_precision_boundary(value, numeric):
    number, reason = excel_number(value)
    assert (number is not None) == numeric
    assert bool(reason) != numeric


def test_roi_pixel_mapping_including_rounding():
    p = PageInfo(210, 297)
    a = Anchor("a", "h", 1, (13.2, 20.3, 30.1, 10.9))
    box = crop_box(a, p, 2481, 3508)
    x, y = pixel_to_mm(0, 0, p, 2481, 3508, box[:2])
    assert 0 <= a.rect[0]-x <= p.width_mm/2481
    assert 0 <= a.rect[1]-y <= p.height_mm/3508
    assert pixel_to_mm(4, 7, p, 2481, 3508, box[:2]) == pixel_to_mm(box[0]+4, box[1]+7, p, 2481, 3508)


def test_zero_ocr_and_reocr_unchanged(app, sample):
    _, _, record = sample
    complete(app, record)
    before = app.store.record(record)
    jobs = app.ocr_jobs(record)
    app.finish_job(jobs[0], {"text": "", "regions": [], "engine": {"fixture": True}})
    assert app.candidates(record, "part") == []
    assert app.store.record(record) == before
    job = jobs[1]
    app.finish_job(job, {"text": "23.0 ℃", "regions": [{"text": "23.0 ℃", "confidence": .98, "polygon_mm": [[10, 40], [30, 40], [30, 46], [10, 46]]}], "engine": {"fixture": True}})
    assert app.store.record(record) == before
    app.finish_job(job, {"text": "changed", "regions": [], "engine": {}})
    assert app.candidates(record, "temp")[0]["text"] == "23.0 ℃"
    assert len(app.ocr_jobs(record)) == 3


def test_geometry_mismatch_keeps_fields_and_profile_versions(app, sample, workdir):
    _, p, _ = sample
    path = workdir/"other.xdw"
    path.write_bytes(b"different source")
    source = app.prepare_source(path)
    app.finish_job("inspect-"+source, {"pages": [{"width_mm": 297, "height_mm": 210, "rotation": 90}]})
    record = app.apply_profile(source, p.id, 1)
    r = app.store.record(record)
    assert len(r["data"]["fields"]) == 3
    assert not r["data"]["geometry_matches"]
    with pytest.raises(RuleError):
        app.ocr_jobs(record)
    app.register_profile(replace(p, version=2, name="New"))
    assert app.context(record)[2].name == "Test"
    with pytest.raises(RuleError):
        app.register_profile(p)
    a = Anchor(source, app.source(source).sha256, 1, (10, 10, 10, 10))
    app.edit(record, "part", 0, value="manual", unit="", raw="manual", anchor=a)
    app.accept(record, "part", 1)


def test_output_frozen_exact_types_and_literal_formula(app, sample):
    _, p, record = sample
    complete(app, record)
    r = app.store.record(record)
    s = state_from(r["data"]["fields"]["part"])
    app.edit(record, "part", r["revision"], value="=1+1", unit="", raw="=1+1", anchor=s.anchor)
    app.accept(record, "part", app.store.record(record)["revision"])
    id = app.finalize()
    artifacts = app.export(id)
    assert all(r["status"] == "complete" for r in artifacts)
    csvpath = app.store.path(next(r["path"] for r in artifacts if r["name"].endswith(".csv")))
    with csvpath.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[1][rows[0].index("部品番号")] == "=1+1"
    assert rows[1][rows[0].index("温度")] == "25.0"
    before = app.dataset(id)
    r = app.store.record(record)
    app.edit(record, "part", r["revision"], value="changed", unit="", raw="", anchor=s.anchor)
    assert app.dataset(id) == before
    with pytest.raises(RuleError):
        app.finalize()


def test_export_failure_only_retry_and_numeric_text(app, sample, monkeypatch):
    _, _, record = sample
    complete(app, record)
    r = app.store.record(record)
    s = state_from(r["data"]["fields"]["temp"])
    app.edit(record, "temp", r["revision"], value="1234567890123456.125", raw="１２３４５６７８９０１２３４５６.１２５℃", unit="℃", anchor=s.anchor)
    app.accept(record, "temp", app.store.record(record)["revision"])
    id = app.finalize()
    original = os.replace
    def failure(src, dst):
        if str(dst).endswith(".xlsx"):
            raise PermissionError("fixture file locked")
        return original(src, dst)
    monkeypatch.setattr(os, "replace", failure)
    artifacts = app.export(id)
    assert [r["status"] for r in artifacts] == ["failed", "complete"]
    path = app.store.path(artifacts[1]["path"])
    time = path.stat().st_mtime_ns
    monkeypatch.setattr(os, "replace", original)
    assert all(r["status"] == "complete" for r in app.export(id))
    assert path.stat().st_mtime_ns == time
    assert app.dataset(id)["groups"][0]["records"][0]["fields"]["temp"]["value"] == "1234567890123456.125"


def test_overlong_excel_not_truncated_csv_survives(app, sample):
    _, _, record = sample
    complete(app, record)
    r = app.store.record(record)
    s = state_from(r["data"]["fields"]["part"])
    text = "あ"*32768
    app.edit(record, "part", r["revision"], value=text, unit="", raw=text, anchor=s.anchor)
    app.accept(record, "part", app.store.record(record)["revision"])
    id = app.finalize()
    artifacts = app.export(id)
    assert [r["status"] for r in artifacts] == ["failed", "complete"]
    assert text in app.store.path(artifacts[1]["path"]).read_text(encoding="utf-8-sig")


def test_save_failure_preserves_revision(app, sample):
    _, _, record = sample
    r = app.store.record(record)
    app.store.db.execute("PRAGMA query_only=ON")
    with pytest.raises(sqlite3.OperationalError):
        app.edit(record, "part", 0, value="unsaved", unit="", raw="", anchor=None)
    app.store.db.execute("PRAGMA query_only=OFF")
    assert app.store.record(record) == r


def test_source_tamper_rejected_and_paths_bounded(app, sample):
    source, _, record = sample
    with pytest.raises(RuleError):
        app.store.path("../escape")
    s = app.source(source)
    app.store.path(s.path).write_bytes(b"tampered")
    with pytest.raises(RuleError):
        app.store.verify()
    from dw_workbench.workers import native
    with pytest.raises(RuleError):
        native(app.worker_request(app.job(app.render_job(source, 1)), app.store.root))


def test_lock_backup_restore_and_reopen(app, sample, workdir):
    _, _, record = sample
    complete(app, record)
    id = app.finalize()
    app.export(id)
    with pytest.raises(RuleError):
        Workbench(app.store.root)
    backup = workdir/"復元用 空白"
    app.store.backup(backup)
    restored = Workbench(backup)
    try:
        assert restored.store.verify()
        assert restored.store.record(record) == app.store.record(record)
        assert restored.dataset(id) == app.dataset(id)
        assert restored.profiles() == app.profiles()
    finally:
        restored.close()


def test_interrupted_jobs_recover_and_no_candidate_duplicates(app, sample, workdir):
    _, _, record = sample
    job = app.ocr_jobs(record)[0]
    app.start_job(job)
    backup = workdir/"restart"
    app.store.backup(backup)
    restored = Workbench(backup)
    try:
        assert restored.job(job)["status"] == "pending"
        restored.finish_job(job, error="GPU unavailable")
        assert restored.job(job)["status"] == "failed"
        assert len(restored.store.record(record)["data"]["fields"]) == 3
        restored.start_job(job)
        restored.finish_job(job, {"text": "", "regions": [], "engine": {}})
        assert restored.job(job)["status"] == "complete"
    finally:
        restored.close()


def test_explicit_subset_and_unassigned_source(app, sample, workdir):
    _, _, record = sample
    complete(app, record)
    path = workdir/"unassigned.xdw"
    path.write_bytes(b"fixture")
    source = app.prepare_source(path)
    app.finish_job("inspect-"+source, {"pages": [{"width_mm": 210, "height_mm": 297, "rotation": 0}]})
    with pytest.raises(RuleError):
        app.finalize()
    id = app.finalize(completed_only=True)
    assert len(app.dataset(id)["excluded"]) == 1


def test_cache_damage_requeues_render(app, sample):
    source, _, record = sample
    path = app.store.path(f"cache/{source}/page-1-300.png")
    path.parent.mkdir(parents=True)
    path.write_bytes(b"cache fixture")
    job = app.render_job(source, 1, 300)
    app.finish_job(job, {"image_sha256": digest(path)})
    assert app.job(app.render_job(source, 1, 300))["status"] == "complete"
    path.write_bytes(b"corrupt cache")
    assert app.job(app.render_job(source, 1, 300))["status"] == "pending"


def test_immutable_machine_and_finalized_tables(app, sample):
    _, p, record = sample
    complete(app, record)
    id = app.finalize()
    with pytest.raises(sqlite3.IntegrityError):
        app.store.db.execute("UPDATE datasets SET data='{}' WHERE id=?", (id,))
    with pytest.raises(sqlite3.IntegrityError):
        app.store.db.execute("UPDATE profiles SET data='{}' WHERE id=?", (p.id,))


def test_failed_backup_rejected(app, workdir, monkeypatch):
    import dw_workbench.storage as storage
    target = workdir/"incomplete"
    monkeypatch.setattr(storage.shutil, "copytree", lambda *a, **k: (_ for _ in ()).throw(PermissionError("fixture")))
    with pytest.raises(PermissionError):
        app.store.backup(target)
    assert (target/"INCOMPLETE.txt").is_file()
    with pytest.raises(RuleError):
        Workbench(target)


def test_excel_literal_escapes_carriage_return_and_supplementary(app, sample):
    _, _, record = sample
    complete(app, record)
    r = app.store.record(record)
    s = state_from(r["data"]["fields"]["part"])
    text = "_x0001_\r\n=literal 😀"
    app.edit(record, "part", r["revision"], value=text, raw=text, unit="", anchor=s.anchor)
    app.accept(record, "part", app.store.record(record)["revision"])
    id = app.finalize()
    assert all(row["status"] == "complete" for row in app.export(id))


def test_gpu_unavailable_manual_completion(app, sample, workdir, monkeypatch):
    import sys
    from types import SimpleNamespace
    from PIL import Image
    from docuworks_integrations.paddle import PaddleOcrEngine
    models = workdir/"models"
    for name in ("PP-OCRv6_medium_det", "PP-OCRv6_medium_rec"):
        (models/name).mkdir(parents=True)
        (models/name/"inference.yml").write_text("fixture")
    path = workdir/"crop.png"
    Image.new("RGB", (100, 40), "white").save(path)
    monkeypatch.setenv("DW_OCR_CACHE", str(workdir/"cache"))
    previous = os.environ.get("USERPROFILE")
    monkeypatch.setitem(sys.modules, "paddle", SimpleNamespace(is_compiled_with_cuda=lambda: False))
    with pytest.raises(RuntimeError, match="CUDA GPU"):
        PaddleOcrEngine(models).recognize(path)
    assert os.environ.get("USERPROFILE") == previous
    complete(app, sample[2])
    assert app.finalize()


def test_unregistered_source_must_be_explicitly_excluded(app, sample, workdir):
    complete(app, sample[2])
    path = workdir/"failed-import.xdw"
    path.write_bytes(b"invalid fixture")
    source = app.prepare_source(path)
    app.finish_job("inspect-"+source, error="DocuWorks refused document")
    with pytest.raises(RuleError):
        app.finalize()
    result = app.dataset(app.finalize(completed_only=True))
    assert result["excluded"][0]["fields"] == ["原本登録未完了"]


def test_reason_edit_autosave_does_not_allow_reasonless_not_applicable(app, sample):
    record = sample[2]
    complete(app, record)
    r = app.store.record(record)
    s = state_from(r["data"]["fields"]["note"])
    app.edit(record, "note", r["revision"], value=s.value, unit=s.unit, raw=s.raw, anchor=s.anchor, reason="")
    assert app.store.record(record)["data"]["fields"]["note"]["status"] != Status.NOT_APPLICABLE
    with pytest.raises(RuleError):
        app.finalize()


def test_backup_releases_destination_handle(app, sample, workdir):
    import psutil
    target = workdir/"backup closed handle"
    app.store.backup(target)
    backup_db = str((target/"project.sqlite").resolve()).casefold()
    assert backup_db not in {f.path.casefold() for f in psutil.Process().open_files()}


def test_stale_file_validation_rejected(app, sample):
    from dw_workbench.storage import validate_sources
    source, _, record = sample
    complete(app, record)
    proof = validate_sources(app.store.root, app.store.verify_database())
    s = app.source(source)
    app.store.path(s.path).write_bytes(b"changed after validation")
    with pytest.raises(RuleError):
        app.finalize(validation=proof)
