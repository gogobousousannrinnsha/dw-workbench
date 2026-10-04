"""Portable-contained immutable template catalog; projects import complete snapshots."""
from dataclasses import asdict
from pathlib import Path
import json
import sqlite3

from .domain import RuleError, profile_from, schema_from
from .storage import encode


class TemplateLibrary:
    FORMAT = 1

    def __init__(self, portable_root):
        self.root = Path(portable_root).resolve()
        self.path = self.root / "settings" / "templates.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, isolation_level=None)
        try:
            self.db.execute("PRAGMA journal_mode=DELETE")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("PRAGMA foreign_keys=ON")
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, self.FORMAT):
                raise RuleError("共通テンプレートの保存形式は対応していません")
            self.db.execute("BEGIN IMMEDIATE")
            self.db.execute("CREATE TABLE IF NOT EXISTS schemas(id TEXT, version INTEGER, data TEXT NOT NULL, PRIMARY KEY(id,version))")
            self.db.execute("""CREATE TABLE IF NOT EXISTS templates(id TEXT, version INTEGER, schema_id TEXT NOT NULL,
                schema_version INTEGER NOT NULL, data TEXT NOT NULL, PRIMARY KEY(id,version),
                FOREIGN KEY(schema_id,schema_version) REFERENCES schemas(id,version))""")
            for table in ("schemas", "templates"):
                for operation in ("UPDATE", "DELETE"):
                    self.db.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'immutable catalog snapshot'); END")
            self.db.execute("PRAGMA user_version=1")
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            self.db.close()
            raise

    def list_profiles(self):
        profiles = [profile_from(json.loads(row[0])) for row in self.db.execute("SELECT data FROM templates")]
        return sorted(profiles, key=lambda item: (item.name.casefold(), item.id, item.version))

    def get_profile(self, id, version):
        row = self.db.execute("SELECT data FROM templates WHERE id=? AND version=?", (id, version)).fetchone()
        if row is None:
            raise RuleError("共通テンプレートに指定した版がありません")
        return profile_from(json.loads(row[0]))

    def get_schema(self, id, version):
        row = self.db.execute("SELECT data FROM schemas WHERE id=? AND version=?", (id, version)).fetchone()
        if row is None:
            raise RuleError("共通テンプレートに項目定義がありません")
        return schema_from(json.loads(row[0]))

    def publish(self, profile, schema):
        profile.validate()
        schema.validate()
        if (profile.schema_id, profile.schema_version) != (schema.id, schema.version) or profile.fields != schema.fields:
            raise RuleError("テンプレートの項目定義と登録する定義が一致しません")
        profile_data, schema_data = asdict(profile), asdict(schema)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self._put_schema(schema.id, schema.version, schema_data)
            row = self.db.execute("SELECT data FROM templates WHERE id=? AND version=?", (profile.id, profile.version)).fetchone()
            if row is not None:
                if json.loads(row[0]) != json.loads(encode(profile_data)):
                    raise RuleError("同じテンプレートID・版に異なる内容が登録されています")
            else:
                self.db.execute("INSERT INTO templates VALUES(?,?,?,?,?)", (profile.id, profile.version, schema.id, schema.version, encode(profile_data)))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def _put_schema(self, id, version, data):
        row = self.db.execute("SELECT data FROM schemas WHERE id=? AND version=?", (id, version)).fetchone()
        if row is not None:
            if json.loads(row[0]) != json.loads(encode(data)):
                raise RuleError("同じ項目定義ID・版に異なる内容が登録されています")
        else:
            self.db.execute("INSERT INTO schemas VALUES(?,?,?)", (id, version, encode(data)))

    def close(self):
        self.db.close()
