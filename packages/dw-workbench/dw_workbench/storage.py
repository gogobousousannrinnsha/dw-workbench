"""Single-writer SQLite repository and bounded file access."""
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from dataclasses import asdict
from .domain import StaleRevision, RuleError, ResultSchema, identifier, timestamp, profile_from, schema_from, source_from


class MigrationRequired(RuleError):
    """The caller must migrate a separate copy; opening never upgrades v1 in place."""
    def __init__(self, root):
        self.root = Path(root).resolve()
        super().__init__("v0.1.0の案件です。元の案件を残して、v0.2.0用のコピーを作成してください")


def legacy_schema_id(profile_id, version):
    return "legacy-" + uuid.uuid5(uuid.NAMESPACE_URL, f"dw-workbench:profile:{profile_id}:{version}").hex


RECORDS_SQL = """CREATE TABLE {table}(id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
    profile_id TEXT NOT NULL, profile_version INTEGER NOT NULL, revision INTEGER NOT NULL, data TEXT NOT NULL,
    page INTEGER, active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), assignment_revision INTEGER NOT NULL DEFAULT 0,
    CHECK(page IS NULL OR page > 0), FOREIGN KEY(profile_id,profile_version) REFERENCES profiles(id,version))"""

SCHEMA_STATEMENTS = [
    "CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, data TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS profiles(id TEXT, version INTEGER, data TEXT NOT NULL, PRIMARY KEY(id,version))",
    RECORDS_SQL.format(table="IF NOT EXISTS records"),
    "CREATE TABLE IF NOT EXISTS observations(id TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES records(id), data TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS candidates(id TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES records(id), data TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL, data TEXT NOT NULL, result TEXT, error TEXT)",
    "CREATE TABLE IF NOT EXISTS datasets(id TEXT PRIMARY KEY, data TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS artifacts(dataset_id TEXT REFERENCES datasets(id), name TEXT, status TEXT, path TEXT, error TEXT, sha256 TEXT, PRIMARY KEY(dataset_id,name))",
    "CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, created TEXT, kind TEXT, target TEXT, revision INTEGER)",
    "CREATE TABLE IF NOT EXISTS schemas(id TEXT, version INTEGER, data TEXT NOT NULL, PRIMARY KEY(id,version))",
    """CREATE TABLE IF NOT EXISTS profile_schemas(profile_id TEXT, profile_version INTEGER,
        schema_id TEXT NOT NULL, schema_version INTEGER NOT NULL, PRIMARY KEY(profile_id,profile_version),
        FOREIGN KEY(profile_id,profile_version) REFERENCES profiles(id,version),
        FOREIGN KEY(schema_id,schema_version) REFERENCES schemas(id,version))""",
    """CREATE TABLE IF NOT EXISTS source_modes(source_id TEXT PRIMARY KEY REFERENCES sources(id),
        mode TEXT NOT NULL CHECK(mode IN ('document','page')), revision INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS page_assignments(source_id TEXT REFERENCES sources(id), page INTEGER NOT NULL CHECK(page>=0),
        revision INTEGER NOT NULL, state TEXT NOT NULL CHECK(state IN ('unassigned','applied','excluded')),
        current_record_id TEXT REFERENCES records(id), reason TEXT NOT NULL DEFAULT '', PRIMARY KEY(source_id,page),
        CHECK((state='applied' AND current_record_id IS NOT NULL) OR (state!='applied' AND current_record_id IS NULL)),
        CHECK(state!='excluded' OR length(trim(reason))>0))""",
    "CREATE INDEX IF NOT EXISTS candidate_record ON candidates(record_id)",
    "CREATE INDEX IF NOT EXISTS observation_record ON observations(record_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS active_document_record ON records(source_id) WHERE active=1 AND page IS NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS active_page_record ON records(source_id,page) WHERE active=1 AND page IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS record_history ON records(source_id,page)",
    """CREATE TRIGGER IF NOT EXISTS immutable_archived_record BEFORE UPDATE OF data,revision ON records
        WHEN OLD.active=0 BEGIN SELECT RAISE(ABORT,'immutable archived record'); END""",
]
for _table in ("profiles", "sources", "observations", "candidates", "datasets", "schemas", "profile_schemas"):
    SCHEMA_STATEMENTS.append(f"CREATE TRIGGER IF NOT EXISTS immutable_{_table} BEFORE UPDATE ON {_table} BEGIN SELECT RAISE(ABORT,'immutable {_table}'); END")


def readonly_database(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, isolation_level=None)


def _install_schema(db):
    for statement in SCHEMA_STATEMENTS:
        db.execute(statement)


def encode(obj):
    return json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fingerprint(path):
    stat = Path(path).stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def relative_path(root, relative):
    if not isinstance(relative, str) or not relative:
        raise RuleError("案件内の相対パスが必要です")
    candidate = Path(relative)
    # Windows 'C:foo' is not absolute, yet carries a drive and cannot move portably.
    if candidate.is_absolute() or candidate.drive or candidate.root:
        raise RuleError("案件内の相対パスが必要です")
    root = Path(root).resolve()
    result = (root / relative).resolve()
    if not result.is_relative_to(root) or result == root:
        raise RuleError("案件外へのパスです")
    return result


class ValidatedSources:
    """Ephemeral proof from a file-verification task, never persisted or accepted from JSON."""
    def __init__(self, root, entries):
        self.root, self.entries = Path(root).resolve(), entries

    def check(self, root, snapshots):
        if self.root != Path(root).resolve():
            raise RuleError("原本検証の案件が一致しません")
        for data in snapshots:
            entry = self.entries.get(data["id"])
            path = relative_path(self.root, data["path"])
            if entry is None or entry[:2] != (data["path"], data["sha256"]) or entry[2] != fingerprint(path):
                raise RuleError("検証後に原本が変わりました。検証をやり直してください")


def validate_sources(root, snapshots):
    root = Path(root).resolve()
    entries = {}
    for data in snapshots:
        path = relative_path(root, data["path"])
        before = fingerprint(path)
        if digest(path) != data["sha256"] or fingerprint(path) != before:
            raise RuleError("固定原本のハッシュが変わっています: "+data["name"])
        entries[data["id"]] = (data["path"], data["sha256"], before)
    return ValidatedSources(root, entries)


def atomic_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + identifier() + ".tmp")
    try:
        with temp.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class FileLock:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = path.open("a+b")
        try:
            self.stream.seek(0)
            if not self.stream.read(1):
                self.stream.write(b"0")
                self.stream.flush()
            self.stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.stream.close()
            raise RuleError("別のアプリがこの案件を開いています") from exc

    def close(self):
        if not self.stream.closed:
            self.stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            self.stream.close()


class Store:
    FORMAT = 2

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        if (self.root/"INCOMPLETE.txt").exists():
            raise RuleError("未完了のコピーです。移行またはバックアップが完了した案件を選んでください")
        self.lock = FileLock(self.root / ".project.lock")
        try:
            database_path = self.root / "project.sqlite"
            if database_path.exists():
                probe = readonly_database(database_path)
                try:
                    version = probe.execute("PRAGMA user_version").fetchone()[0]
                finally:
                    probe.close()
                if version == 1:
                    raise MigrationRequired(self.root)
                if version not in (0, self.FORMAT):
                    raise RuleError("この案件の保存形式は対応していません")
            for name in ("sources", "cache", "staging", "exports", "logs"):
                (self.root / name).mkdir(exist_ok=True)
            self.db = sqlite3.connect(self.root / "project.sqlite", isolation_level=None)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA journal_mode=DELETE")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("PRAGMA foreign_keys=ON")
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, self.FORMAT):
                raise RuleError("この案件の保存形式は対応していません")
            with self.transaction():
                _install_schema(self.db)
                self.db.execute("PRAGMA user_version=2")
            # A crashed/incomplete worker has no authority to mark completion.
            self.db.execute("UPDATE jobs SET status='pending' WHERE status='running'")
        except BaseException:
            if hasattr(self, "db"):
                self.db.close()
            self.lock.close()
            raise

    def path(self, relative):
        return relative_path(self.root, relative)

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def event(self, kind, target, revision=None):
        self.db.execute("INSERT INTO events(created,kind,target,revision) VALUES(?,?,?,?)", (timestamp(), kind, target, revision))

    def record(self, id):
        r = self.db.execute("SELECT * FROM records WHERE id=?", (id,)).fetchone()
        if r is None:
            raise RuleError("記録が見つかりません")
        return dict(r) | {"data": json.loads(r["data"])}

    def update(self, id, expected_revision, data, kind="edit"):
        if not self.record(id)["active"]:
            raise RuleError("変更前の履歴は編集できません。現在の記録を選んでください")
        revision = expected_revision + 1
        cursor = self.db.execute("UPDATE records SET data=?,revision=? WHERE id=? AND revision=? AND active=1", (encode(data), revision, id, expected_revision))
        if cursor.rowcount != 1:
            raise StaleRevision("古い版からの保存を拒否しました。保存済みの状態を再表示してください")
        self.event(kind, id, revision)
        return revision

    def rows(self, table):
        if table not in ("sources", "profiles", "records", "jobs", "datasets", "artifacts", "schemas", "profile_schemas", "source_modes", "page_assignments", "observations", "candidates", "events"):
            raise ValueError(table)
        return [dict(r) for r in self.db.execute("SELECT * FROM " + table)]

    def backup(self, destination):
        destination = self.begin_backup(destination)
        complete_backup(self.root, destination)

    def begin_backup(self, destination):
        destination = Path(destination).resolve()
        if destination.exists() or destination.is_relative_to(self.root):
            raise RuleError("バックアップ先は案件外の新しいフォルダーにしてください")
        destination.mkdir(parents=True)
        try:
            atomic_bytes(destination/"INCOMPLETE.txt", b"Backup has not completed. Do not restore.")
            target = sqlite3.connect(destination / "project.sqlite")
            try:
                self.db.backup(target)
            finally:
                target.close()
            atomic_bytes(destination/"INCOMPLETE.txt", b"Backup has not completed. Do not restore.")
            return destination
        except BaseException:
            # Preserve a failed backup for diagnosis; never present it as completed.
            atomic_bytes(destination/"INCOMPLETE.txt", b"Backup did not complete. Do not restore.")
            raise

    def verify_database(self):
        if self.db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or self.db.execute("PRAGMA foreign_key_check").fetchall():
            raise RuleError("案件データの整合性検査に失敗しました")
        # Foreign keys alone cannot prove that the current record belongs to this page.
        invalid = self.db.execute("""SELECT r.id FROM records r LEFT JOIN page_assignments a ON a.current_record_id=r.id
            WHERE r.active=1 AND (a.current_record_id IS NULL OR a.state!='applied' OR a.source_id!=r.source_id
                OR a.page!=COALESCE(r.page,0) OR a.revision!=r.assignment_revision) LIMIT 1""").fetchone()
        invalid_assignment = self.db.execute("""SELECT a.source_id FROM page_assignments a JOIN records r ON a.current_record_id=r.id
            WHERE a.state='applied' AND (r.active!=1 OR a.source_id!=r.source_id OR a.page!=COALESCE(r.page,0)
                OR a.revision!=r.assignment_revision) LIMIT 1""").fetchone()
        if invalid or invalid_assignment:
            raise RuleError("現在のページ割当と記録が一致しません")
        source_rows = self.rows("sources")
        snapshots = [json.loads(row["data"]) for row in source_rows]
        if any(row["id"] != data["id"] for row, data in zip(source_rows, snapshots)):
            raise RuleError("原本のIDが案件データと一致しません")
        sources = {data["id"]: source_from(data) for data in snapshots}
        modes = {row["source_id"]: row["mode"] for row in self.rows("source_modes")}
        targets = {id: set() for id in modes}
        for row in self.rows("page_assignments"):
            if row["source_id"] not in targets:
                raise RuleError("ページ割当に処理方式がありません")
            targets[row["source_id"]].add(row["page"])
        for id, mode in modes.items():
            expected = {0} if mode == "document" else set(range(1, len(sources[id].pages)+1))
            if targets[id] != expected:
                raise RuleError("処理方式と対象ページの構成が一致しません")
        definitions = {}
        for row in self.rows("schemas"):
            schema = schema_from(json.loads(row["data"]))
            schema.validate()
            if (schema.id, schema.version) != (row["id"], row["version"]):
                raise RuleError("項目定義のID・版が一致しません")
            definitions[schema.id, schema.version] = schema
        bindings = {(row["profile_id"], row["profile_version"]): (row["schema_id"], row["schema_version"])
            for row in self.rows("profile_schemas")}
        for row in self.rows("profiles"):
            profile = profile_from(json.loads(row["data"]))
            profile.validate()
            binding = bindings.get((row["id"], row["version"]))
            if (profile.id, profile.version) != (row["id"], row["version"]) or binding is None:
                raise RuleError("テンプレートのID・版・項目定義が一致しません")
            if profile.schema_id and (profile.schema_id, profile.schema_version) != binding:
                raise RuleError("テンプレートの項目定義版が一致しません")
            if definitions[binding].fields != profile.fields:
                raise RuleError("テンプレートの項目と項目定義が一致しません")
        return snapshots

    def verify(self, validation=None):
        snapshots = self.verify_database()
        validation = validation or validate_sources(self.root, snapshots)
        if not isinstance(validation, ValidatedSources):
            raise RuleError("原本検証の結果が不正です")
        validation.check(self.root, snapshots)
        return True

    def close(self):
        self.db.close()
        self.lock.close()


def complete_backup(source, destination):
    source, destination = Path(source), Path(destination)
    for name in ("sources", "exports"):
        shutil.copytree(source/name, destination/name)
    if (source / "drafts").is_dir():
        shutil.copytree(source / "drafts", destination / "drafts")
    # Copy success is not proof that the copied fixed originals match the DB snapshot.
    db = readonly_database(destination / "project.sqlite")
    try:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchall():
            raise RuleError("バックアップした案件データの整合性検査に失敗しました")
        snapshots = [json.loads(row[0]) for row in db.execute("SELECT data FROM sources")]
        validate_sources(destination, snapshots)
    finally:
        db.close()
    manifest = {p.relative_to(destination).as_posix(): digest(p) for p in destination.rglob("*") if p.is_file() and p.name != "INCOMPLETE.txt"}
    atomic_bytes(destination/"backup-manifest.json", encode(manifest).encode("utf-8"))
    (destination/"INCOMPLETE.txt").unlink()


def _migrate_v1_database(db):
    """Upgrade the copied database atomically, preserving every original JSON payload."""
    if db.execute("PRAGMA user_version").fetchone()[0] != 1:
        raise RuleError("移行対象はv0.1.0の案件に限ります")
    # The documented SQLite rebuild procedure keeps child references to 'records'.
    db.execute("PRAGMA foreign_keys=OFF")
    db.execute("BEGIN IMMEDIATE")
    try:
        db.execute(RECORDS_SQL.format(table="records_v2"))
        db.execute("""INSERT INTO records_v2(id,source_id,profile_id,profile_version,revision,data,page,active,assignment_revision)
            SELECT id,source_id,profile_id,profile_version,revision,data,NULL,1,1 FROM records""")
        db.execute("DROP TABLE records")
        db.execute("ALTER TABLE records_v2 RENAME TO records")
        _install_schema(db)
        for row in db.execute("SELECT id,version,data FROM profiles").fetchall():
            profile = profile_from(json.loads(row[2]))
            profile.validate()
            if (profile.id, profile.version) != (row[0], row[1]):
                raise RuleError("旧テンプレートのID・版が一致しません")
            schema = ResultSchema(legacy_schema_id(row[0], row[1]), 1, profile.name, profile.fields)
            schema.validate()
            db.execute("INSERT INTO schemas VALUES(?,?,?)", (schema.id, schema.version, encode(asdict(schema))))
            db.execute("INSERT INTO profile_schemas VALUES(?,?,?,?)", (row[0], row[1], schema.id, schema.version))
        db.execute("INSERT INTO source_modes(source_id,mode,revision) SELECT id,'document',0 FROM sources")
        db.execute("""INSERT INTO page_assignments(source_id,page,revision,state,current_record_id,reason)
            SELECT s.id,0,CASE WHEN r.id IS NULL THEN 0 ELSE 1 END,
                CASE WHEN r.id IS NULL THEN 'unassigned' ELSE 'applied' END,r.id,''
            FROM sources s LEFT JOIN records r ON r.source_id=s.id""")
        db.execute("PRAGMA user_version=2")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchall():
            raise RuleError("移行後の案件データの整合性検査に失敗しました")
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise
    finally:
        db.execute("PRAGMA foreign_keys=ON")


def migrate_project_copy(root, destination_parent=None):
    """Make a verified v2 copy. Never change the v1 database or fixed originals."""
    root = Path(root).resolve()
    if not root.is_dir() or not (root / "project.sqlite").is_file():
        raise RuleError("移行する案件フォルダーが見つかりません")
    if (root / "INCOMPLETE.txt").exists():
        raise RuleError("未完了のコピーは移行できません")
    parent = root.parent if destination_parent is None else Path(destination_parent).resolve()
    if parent == root or parent.is_relative_to(root):
        raise RuleError("移行先は元の案件フォルダーの外にしてください")
    lock = FileLock(root / ".project.lock")
    source_db = target_db = None
    destination = None
    try:
        source_db = readonly_database(root / "project.sqlite")
        if source_db.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise RuleError("移行対象はv0.1.0の案件に限ります")
        if source_db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or source_db.execute("PRAGMA foreign_key_check").fetchall():
            raise RuleError("元の案件データの整合性検査に失敗しました")
        snapshots = [json.loads(row[0]) for row in source_db.execute("SELECT data FROM sources")]
        original_proof = validate_sources(root, snapshots)
        original_hash = digest(root / "project.sqlite")
        parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(32):
            destination = parent / (root.name + " v0.2.0 " + identifier()[:8])
            try:
                destination.mkdir()
                break
            except FileExistsError:
                continue
        else:
            raise RuleError("移行先の新しいフォルダーを作成できません")
        atomic_bytes(destination / "INCOMPLETE.txt", b"Migration has not completed. Do not open or restore.")
        target_db = sqlite3.connect(destination / "project.sqlite", isolation_level=None)
        source_db.backup(target_db)
        target_db.execute("PRAGMA journal_mode=DELETE")
        target_db.execute("PRAGMA synchronous=FULL")
        for name in ("sources", "exports"):
            if (root / name).is_dir():
                shutil.copytree(root / name, destination / name)
            else:
                (destination / name).mkdir()
        if (root / "drafts").is_dir():
            shutil.copytree(root / "drafts", destination / "drafts")
        for name in ("cache", "staging", "logs"):
            (destination / name).mkdir()
        _migrate_v1_database(target_db)
        validate_sources(destination, snapshots)
        original_proof.check(root, snapshots)
        if digest(root / "project.sqlite") != original_hash:
            raise RuleError("移行中に元の案件データが変わりました")
        # Validate copied output bytes too; preserving old artifacts must not be inferred from copytree.
        files = {}
        for directory in ("sources", "exports", "drafts"):
            for path in (root / directory).rglob("*"):
                if path.is_file():
                    relative = path.relative_to(root).as_posix()
                    expected = digest(path)
                    if digest(destination / relative) != expected:
                        raise RuleError("移行したファイルが元の案件と一致しません: " + relative)
                    files[relative] = expected
        target_db.close()
        target_db = None
        atomic_bytes(destination / "migration-manifest.json", encode({"from_format": 1, "to_format": 2,
            "original_database_sha256": original_hash, "created": timestamp(), "files": files}).encode("utf-8"))
        (destination / "INCOMPLETE.txt").unlink()
        return destination
    finally:
        if target_db is not None:
            target_db.close()
        if source_db is not None:
            source_db.close()
        lock.close()
