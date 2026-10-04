"""Independent persistence/catalog/migration tests without UI or native SDK dependencies."""
from dataclasses import asdict, replace
from pathlib import Path
import json
import os
import shutil
import sqlite3

import pytest

from dw_workbench.domain import (ExtractionProfile, FieldSchema, PageInfo, ResultSchema,
    RuleError, SourceSnapshot, profile_from, schema_from)
from dw_workbench.library import TemplateLibrary
from dw_workbench.storage import (MigrationRequired, Store, digest, encode, legacy_schema_id,
    migrate_project_copy, relative_path, validate_sources)


def page_template():
    schema = ResultSchema("measurement", 1, "測定項目", (FieldSchema("part", "部品番号"),))
    profile = ExtractionProfile("layout-a", 1, "測定票A", (PageInfo(210, 297),), schema.fields,
        {"part": {"page": 1, "rect": [10, 20, 50, 10]}}, "page", schema.id, schema.version)
    return profile, schema


def v1_fixture(root):
    root.mkdir()
    (root / "sources").mkdir()
    (root / "exports").mkdir()
    (root / "sources" / "fixed.xdw").write_bytes(b"Synthetic fixed original, not an SDK-valid XDW")
    (root / "exports" / "legacy.csv").write_bytes(b"legacy export must remain byte-identical")
    source = SourceSnapshot("source", "旧案件.xdw", digest(root / "sources" / "fixed.xdw"), "sources/fixed.xdw", (PageInfo(210, 297),))
    profile, _ = page_template()
    profile_data = asdict(profile)
    for key in ("scope", "schema_id", "schema_version"):
        profile_data.pop(key)
    db = sqlite3.connect(root / "project.sqlite")
    db.executescript("""
        CREATE TABLE sources(id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE profiles(id TEXT, version INTEGER, data TEXT NOT NULL, PRIMARY KEY(id,version));
        CREATE TABLE records(id TEXT PRIMARY KEY,source_id TEXT UNIQUE NOT NULL REFERENCES sources(id),
            profile_id TEXT, profile_version INTEGER, revision INTEGER, data TEXT,
            FOREIGN KEY(profile_id,profile_version) REFERENCES profiles(id,version));
        CREATE TABLE observations(id TEXT PRIMARY KEY,record_id TEXT REFERENCES records(id),data TEXT);
        CREATE TABLE candidates(id TEXT PRIMARY KEY,record_id TEXT REFERENCES records(id),data TEXT);
        CREATE TABLE jobs(id TEXT PRIMARY KEY,kind TEXT,status TEXT,data TEXT,result TEXT,error TEXT);
        CREATE TABLE datasets(id TEXT PRIMARY KEY,data TEXT);
        CREATE TABLE artifacts(dataset_id TEXT REFERENCES datasets(id),name TEXT,status TEXT,path TEXT,error TEXT,sha256 TEXT,PRIMARY KEY(dataset_id,name));
        CREATE TABLE events(id INTEGER PRIMARY KEY,created TEXT,kind TEXT,target TEXT,revision INTEGER);
        PRAGMA user_version=1;
    """)
    payloads = {
        "source": encode(asdict(source)), "profile": encode(profile_data),
        "record": encode({"fields": {"part": {"value": "001234", "raw": "００１２３４", "status": "accepted", "accepted_revision": 7}}, "geometry_matches": True}),
        "observation": encode({"text": "001234", "immutable": "機械の原文"}),
        "candidate": encode({"text": "001234"}),
        "dataset": encode({"id": "old-dataset", "groups": [{"profile": profile_data, "records": []}], "excluded": []}),
        "job": encode({"record_id": "record", "field_id": "part"}),
    }
    db.execute("INSERT INTO sources VALUES(?,?)", ("source", payloads["source"]))
    db.execute("INSERT INTO profiles VALUES(?,?,?)", (profile.id, profile.version, payloads["profile"]))
    db.execute("INSERT INTO records VALUES(?,?,?,?,?,?)", ("record", "source", profile.id, 1, 7, payloads["record"]))
    db.execute("INSERT INTO observations VALUES(?,?,?)", ("obs", "record", payloads["observation"]))
    db.execute("INSERT INTO candidates VALUES(?,?,?)", ("candidate", "record", payloads["candidate"]))
    db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?)", ("old-job", "ocr", "complete", payloads["job"], "{}", None))
    db.execute("INSERT INTO datasets VALUES(?,?)", ("old-dataset", payloads["dataset"]))
    db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?)", ("old-dataset", "legacy.csv", "complete", "exports/legacy.csv", None, digest(root / "exports" / "legacy.csv")))
    db.execute("INSERT INTO events VALUES(?,?,?,?,?)", (1, "before", "accept", "record", 7))
    db.commit()
    db.close()
    return payloads


def test_page_template_maps_relative_anchor_without_document_page_count():
    profile, schema = page_template()
    schema.validate()
    profile.validate()
    source = SourceSnapshot("source", "three-pages", "sha", "sources/x.xdw", (PageInfo(297, 210, 90), PageInfo(210, 297), PageInfo(210, 297)))
    assert not profile.matches(source, 1)
    assert profile.matches(source, 2)
    assert profile.matches(source, 3)
    assert not profile.matches(source)
    assert profile.resolve_region("part", 3) == {"page": 3, "rect": [10, 20, 50, 10]}
    assert profile.regions["part"]["page"] == 1
    assert schema_from(asdict(schema)) == schema
    assert profile_from(asdict(profile)) == profile
    with pytest.raises(RuleError):
        profile.resolve_region("part")
    with pytest.raises(RuleError):
        replace(profile, regions={"part": {"page": 2, "rect": [10, 20, 50, 10]}}).validate()
    with pytest.raises(RuleError):
        replace(schema, fields=schema.fields * 2).validate()


def test_store_independent_pages_archive_and_active_uniqueness(workdir):
    store = Store(workdir / "new")
    try:
        profile, schema = page_template()
        source = SourceSnapshot("source", "two-pages", "sha", "sources/x.xdw", (PageInfo(210, 297),) * 2)
        store.db.execute("INSERT INTO sources VALUES(?,?)", (source.id, encode(asdict(source))))
        store.db.execute("INSERT INTO profiles VALUES(?,?,?)", (profile.id, 1, encode(asdict(profile))))
        store.db.execute("INSERT INTO schemas VALUES(?,?,?)", (schema.id, 1, encode(asdict(schema))))
        store.db.execute("INSERT INTO profile_schemas VALUES(?,?,?,?)", (profile.id, 1, schema.id, 1))
        sql = "INSERT INTO records(id,source_id,profile_id,profile_version,revision,data,page,assignment_revision) VALUES(?,?,?,?,?,?,?,?)"
        store.db.execute(sql, ("p1", source.id, profile.id, 1, 0, encode({"value": "page1"}), 1, 1))
        store.db.execute(sql, ("p2", source.id, profile.id, 1, 0, encode({"value": "page2"}), 2, 1))
        with pytest.raises(sqlite3.IntegrityError):
            store.db.execute(sql, ("duplicate", source.id, profile.id, 1, 0, "{}", 1, 1))
        store.update("p1", 0, {"value": "edited1"})
        assert store.record("p2")["data"] == {"value": "page2"}
        store.db.execute("UPDATE records SET active=0 WHERE id='p1'")
        store.db.execute(sql, ("replacement", source.id, profile.id, 1, 0, "{}", 1, 2))
        with pytest.raises(RuleError, match="履歴"):
            store.update("p1", 1, {"value": "must not change"})
        with pytest.raises(sqlite3.IntegrityError, match="immutable archived"):
            store.db.execute("UPDATE records SET data='{}' WHERE id='p1'")
        assert store.record("p1")["data"] == {"value": "edited1"}
        assert store.db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert len(store.rows("schemas")) == 1
    finally:
        store.close()


def test_catalog_idempotence_conflicts_and_move(workdir):
    root = workdir / "Portable 日本語"
    library = TemplateLibrary(root)
    profile, schema = page_template()
    try:
        library.publish(profile, schema)
        library.publish(profile, schema)
        assert library.list_profiles() == [profile]
        assert library.get_schema(schema.id, 1) == schema
        with pytest.raises(RuleError, match="異なる内容"):
            library.publish(replace(profile, name="changed"), schema)
        with pytest.raises(RuleError, match="異なる内容"):
            library.publish(profile, replace(schema, name="changed definition"))
        other_schema = replace(schema, id="should-rollback")
        with pytest.raises(RuleError, match="異なる内容"):
            library.publish(replace(profile, schema_id=other_schema.id), other_schema)
        with pytest.raises(RuleError, match="項目定義がありません"):
            library.get_schema(other_schema.id, 1)
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            library.db.execute("DELETE FROM templates")
    finally:
        library.close()
    moved = workdir / "Moved Portable 空白"
    shutil.move(root, moved)
    reopened = TemplateLibrary(moved)
    try:
        assert reopened.get_profile(profile.id, 1) == profile
        assert reopened.get_schema(schema.id, 1) == schema
    finally:
        reopened.close()


def test_v1_open_is_readonly_and_copy_preserves_every_payload(workdir):
    original = workdir / "旧 案件"
    payloads = v1_fixture(original)
    db_hash = digest(original / "project.sqlite")
    with pytest.raises(MigrationRequired) as error:
        Store(original)
    assert error.value.root == original.resolve()
    assert digest(original / "project.sqlite") == db_hash
    assert not (original / "cache").exists()
    migrated = migrate_project_copy(original)
    assert migrated.parent == original.parent and migrated != original
    assert not (migrated / "INCOMPLETE.txt").exists()
    assert digest(original / "project.sqlite") == db_hash
    assert digest(migrated / "exports" / "legacy.csv") == digest(original / "exports" / "legacy.csv")
    store = Store(migrated)
    try:
        for table, key in (("sources", "source"), ("profiles", "profile"), ("records", "record"), ("observations", "observation"), ("candidates", "candidate"), ("datasets", "dataset"), ("jobs", "job")):
            assert store.rows(table)[0]["data"] == payloads[key]
        record = store.record("record")
        assert (record["revision"], record["page"], record["active"], record["assignment_revision"]) == (7, None, 1, 1)
        assert store.rows("source_modes") == [{"source_id": "source", "mode": "document", "revision": 0}]
        assert store.rows("page_assignments")[0]["current_record_id"] == "record"
        assert store.rows("profile_schemas")[0]["schema_id"] == legacy_schema_id("layout-a", 1)
        assert store.rows("artifacts")[0]["path"] == "exports/legacy.csv"
        assert store.rows("events")[0]["target"] == "record"
        assert store.verify()
    finally:
        store.close()


def test_failed_migration_keeps_marker_and_retry_never_mutates_original(workdir, monkeypatch):
    from dw_workbench import storage
    original = workdir / "旧案件"
    v1_fixture(original)
    db_hash = digest(original / "project.sqlite")
    migrate = storage._migrate_v1_database

    def fail(db):
        raise RuntimeError("simulated interruption")

    monkeypatch.setattr(storage, "_migrate_v1_database", fail)
    with pytest.raises(RuntimeError, match="interruption"):
        migrate_project_copy(original)
    failed = next(path for path in workdir.iterdir() if " v0.2.0 " in path.name)
    assert (failed / "INCOMPLETE.txt").exists()
    with pytest.raises(RuleError, match="未完了"):
        Store(failed)
    assert digest(original / "project.sqlite") == db_hash
    monkeypatch.setattr(storage, "_migrate_v1_database", migrate)
    successful = migrate_project_copy(original)
    assert successful != failed and not (successful / "INCOMPLETE.txt").exists()
    assert (failed / "INCOMPLETE.txt").exists()
    assert digest(original / "project.sqlite") == db_hash


def test_migration_rejects_changed_fixed_original_and_releases_lock(workdir):
    original = workdir / "旧案件"
    v1_fixture(original)
    before = digest(original / "project.sqlite")
    (original / "sources" / "fixed.xdw").write_bytes(b"changed")
    with pytest.raises(RuleError, match="ハッシュ"):
        migrate_project_copy(original)
    assert digest(original / "project.sqlite") == before
    assert not any(" v0.2.0 " in path.name for path in workdir.iterdir())
    with pytest.raises(MigrationRequired):
        Store(original)


def test_migration_schema_failure_rolls_back_sql_rebuild(workdir):
    original = workdir / "旧案件"
    v1_fixture(original)
    db = sqlite3.connect(original / "project.sqlite")
    payload = json.loads(db.execute("SELECT data FROM profiles").fetchone()[0])
    payload["id"], payload["name"] = "bad-profile", "不正な旧定義"
    payload["fields"] *= 2
    db.execute("INSERT INTO profiles VALUES(?,?,?)", (payload["id"], 1, encode(payload)))
    db.commit()
    db.close()
    before = digest(original / "project.sqlite")
    with pytest.raises(RuleError, match="重複"):
        migrate_project_copy(original)
    failed = next(path for path in workdir.iterdir() if " v0.2.0 " in path.name)
    assert (failed / "INCOMPLETE.txt").exists()
    db = sqlite3.connect(failed / "project.sqlite")
    try:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        assert [row[1] for row in db.execute("PRAGMA table_info(records)")] == ["id", "source_id", "profile_id", "profile_version", "revision", "data"]
        assert db.execute("SELECT name FROM sqlite_master WHERE name='schemas'").fetchone() is None
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        db.close()
    assert digest(original / "project.sqlite") == before


def test_migration_keeps_distinct_definitions_for_same_named_versions(workdir):
    original = workdir / "旧案件"
    v1_fixture(original)
    db = sqlite3.connect(original / "project.sqlite")
    payload = json.loads(db.execute("SELECT data FROM profiles").fetchone()[0])
    payload["version"] = 2
    db.execute("INSERT INTO profiles VALUES(?,?,?)", (payload["id"], 2, encode(payload)))
    db.commit()
    db.close()
    migrated = migrate_project_copy(original)
    store = Store(migrated)
    try:
        bindings = store.rows("profile_schemas")
        assert len(bindings) == 2 and len({row["schema_id"] for row in bindings}) == 2
        assert [json.loads(row["data"])["name"] for row in store.rows("schemas")] == [payload["name"], payload["name"]]
        assert store.record("record")["profile_version"] == 1
    finally:
        store.close()


def test_backup_and_migration_preserve_unfinished_template_drafts(workdir):
    draft = encode({"source_id": "source", "page": 2, "name": "未完成テンプレート", "regions": {}}).encode("utf-8")
    old = workdir / "旧案件"
    v1_fixture(old)
    (old / "drafts").mkdir()
    (old / "drafts" / "template.json").write_bytes(draft)
    migrated = migrate_project_copy(old)
    assert (migrated / "drafts" / "template.json").read_bytes() == draft
    store = Store(migrated)
    try:
        backup = workdir / "Draft restored"
        store.backup(backup)
        assert (backup / "drafts" / "template.json").read_bytes() == draft
        manifest = json.loads((backup / "backup-manifest.json").read_text(encoding="utf-8"))
        assert manifest["drafts/template.json"] == digest(backup / "drafts" / "template.json")
    finally:
        store.close()


def test_source_validation_refuses_absolute_reference_even_inside_project(workdir):
    root = workdir / "Portable path safety"
    root.mkdir()
    file = root / "original.xdw"
    file.write_bytes(b"fixed source")
    snapshot = {"id": "source", "name": file.name, "path": str(file.resolve()), "sha256": digest(file)}
    with pytest.raises(RuleError, match="相対パス"):
        validate_sources(root, [snapshot])
    proof = validate_sources(root, [snapshot | {"path": "original.xdw"}])
    proof.check(root, [snapshot | {"path": "original.xdw"}])
    with pytest.raises(RuleError, match="相対パス"):
        proof.check(root, [snapshot])


def test_migration_destination_can_be_new_portable_without_touching_old_tree(workdir):
    old_portable = workdir / "v0.1.0 Portable"
    old_portable.mkdir()
    old_project = old_portable / "旧案件"
    v1_fixture(old_project)
    before = digest(old_project / "project.sqlite")
    destination_parent = workdir / "v0.2.0 Portable" / "projects"
    first = migrate_project_copy(old_project, destination_parent)
    second = migrate_project_copy(old_project, destination_parent)
    assert first.parent == destination_parent and second.parent == destination_parent
    assert first != second
    assert list(old_portable.iterdir()) == [old_project]
    assert digest(old_project / "project.sqlite") == before
    with pytest.raises(RuleError, match="外"):
        migrate_project_copy(old_project, old_project / "nested")
    assert not (old_project / "nested").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows drive/root-relative path semantics")
def test_windows_drive_and_root_relative_paths_cannot_be_persisted(workdir):
    root = workdir / "ドライブ相対パス"
    root.mkdir()
    file = root / "original.xdw"
    file.write_bytes(b"fixed source")
    drive_relative = root.drive + "original.xdw"
    root_relative = "\\" + str(file.relative_to(Path(root.anchor)))
    # Both spellings can resolve to the same in-project file on this computer.
    # A containment check alone therefore would accept a nonportable reference.
    assert (root / drive_relative).resolve() == file.resolve()
    assert (root / root_relative).resolve() == file.resolve()
    bad = (drive_relative, root_relative, str(file.resolve()), r"D:original.xdw", r"\\server\share\original.xdw")
    snapshot = {"id": "source", "name": file.name, "path": "original.xdw", "sha256": digest(file)}
    proof = validate_sources(root, [snapshot])
    for path in bad:
        with pytest.raises(RuleError, match="相対パス"):
            relative_path(root, path)
        with pytest.raises(RuleError, match="相対パス"):
            validate_sources(root, [snapshot | {"path": path}])
        with pytest.raises(RuleError, match="相対パス"):
            proof.check(root, [snapshot | {"path": path}])
    assert relative_path(root, "original.xdw") == file.resolve()
    assert relative_path(root, ".\\original.xdw") == file.resolve()
