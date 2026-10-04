"""Application operations; called by the UI thread, never by workers."""
from dataclasses import asdict, replace
from pathlib import Path
import json
import os
import shutil
from .domain import (Anchor, Candidate, ExtractionProfile, FieldState, FinalizedDataset, Observation,
    ResultSchema, PageAssignment, RuleError, StaleRevision, Status, identifier, timestamp,
    profile_from, schema_from, source_from, state_from, unfinished)
from .storage import Store, atomic_bytes, digest, encode, ValidatedSources, validate_sources, fingerprint


def copy_snapshot(filename, project_root):
    filename = Path(filename).resolve()
    if filename.suffix.lower() != ".xdw":
        raise RuleError("初版はXDW文書を登録できます")
    id = identifier()
    root = Path(project_root)
    relative = "sources/"+id+".xdw"
    target, temp = root/relative, root/"staging"/(id+".xdw")
    try:
        before = digest(filename)
        with filename.open("rb") as src, temp.open("xb") as out:
            shutil.copyfileobj(src, out)
            out.flush()
            os.fsync(out.fileno())
        sha = digest(temp)
        if sha != before or digest(filename) != before:
            raise RuleError("コピー中に入力文書が変更されました。安定した原本を再登録してください")
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    return {"id": id, "name": filename.name, "sha256": sha, "path": relative}


class Workbench:
    def __init__(self, root):
        self.store = Store(root)

    def source(self, id):
        row = self.store.db.execute("SELECT data FROM sources WHERE id=?", (id,)).fetchone()
        if row is None:
            raise RuleError("原本がありません")
        return source_from(json.loads(row[0]))

    def profile(self, id, version):
        row = self.store.db.execute("SELECT data FROM profiles WHERE id=? AND version=?", (id, version)).fetchone()
        if row is None:
            raise RuleError("設定がありません")
        profile = profile_from(json.loads(row[0]))
        binding = self.store.db.execute("SELECT schema_id,schema_version FROM profile_schemas WHERE profile_id=? AND profile_version=?", (id, version)).fetchone()
        if binding:
            profile = replace(profile, schema_id=binding[0], schema_version=binding[1])
        return profile

    def profiles(self):
        return [self.profile(r["id"], r["version"]) for r in self.store.rows("profiles")]

    def schemas(self):
        return [schema_from(json.loads(r["data"])) for r in self.store.rows("schemas")]

    def schema(self, id, version):
        row = self.store.db.execute("SELECT data FROM schemas WHERE id=? AND version=?", (id, version)).fetchone()
        if row is None:
            raise RuleError("項目定義がありません")
        return schema_from(json.loads(row[0]))

    def register_schema(self, schema):
        schema.validate()
        with self.store.transaction():
            current = self.store.db.execute("SELECT MAX(version) FROM schemas WHERE id=?", (schema.id,)).fetchone()[0] or 0
            if schema.version != current + 1:
                raise RuleError("項目定義は次の版として登録してください")
            self.store.db.execute("INSERT INTO schemas(id,version,data) VALUES(?,?,?)", (schema.id, schema.version, encode(asdict(schema))))
            self.store.event("schema", schema.id, schema.version)

    def register_template(self, profile, schema):
        """Authoring saves definition and layout in one short transaction."""
        profile.validate()
        schema.validate()
        if (profile.schema_id, profile.schema_version) != (schema.id, schema.version) or profile.fields != schema.fields:
            raise RuleError("テンプレートと項目定義が一致しません")
        with self.store.transaction():
            latest = self.store.db.execute("SELECT MAX(version) FROM profiles WHERE id=?", (profile.id,)).fetchone()[0] or 0
            if profile.version != latest+1:
                raise StaleRevision("テンプレートの登録予定版が古くなっています。登録済みの版を確認してください")
            existing = self.store.db.execute("SELECT data FROM schemas WHERE id=? AND version=?", (schema.id, schema.version)).fetchone()
            if existing:
                if schema_from(json.loads(existing[0])) != schema:
                    raise RuleError("同じ項目定義ID・版で内容が異なります")
            else:
                latest_schema = self.store.db.execute("SELECT MAX(version) FROM schemas WHERE id=?", (schema.id,)).fetchone()[0] or 0
                if schema.version != latest_schema+1:
                    raise StaleRevision("項目定義の登録予定版が古くなっています")
                self.store.db.execute("INSERT INTO schemas VALUES(?,?,?)", (schema.id, schema.version, encode(asdict(schema))))
                self.store.event("schema", schema.id, schema.version)
            self.store.db.execute("INSERT INTO profiles VALUES(?,?,?)", (profile.id, profile.version, encode(asdict(profile))))
            self.store.db.execute("INSERT INTO profile_schemas VALUES(?,?,?,?)", (profile.id, profile.version, schema.id, schema.version))
            self.store.event("profile", profile.id, profile.version)

    def import_template(self, library, id, version):
        profile = library.get_profile(id, version)
        schema = library.get_schema(profile.schema_id, profile.schema_version)
        profile.validate()
        schema.validate()
        if profile.fields != schema.fields:
            raise RuleError("テンプレートと項目定義が一致しません")
        with self.store.transaction():
            for table, obj in (("schemas", schema), ("profiles", profile)):
                existing = self.store.db.execute("SELECT data FROM "+table+" WHERE id=? AND version=?", (obj.id, obj.version)).fetchone()
                if existing:
                    decoded = schema_from(json.loads(existing[0])) if table == "schemas" else self.profile(obj.id, obj.version)
                    if decoded != obj:
                        raise RuleError("同じID・版で内容が異なります。取り込みを中止しました")
                else:
                    self.store.db.execute("INSERT INTO "+table+"(id,version,data) VALUES(?,?,?)", (obj.id, obj.version, encode(asdict(obj))))
            self.store.db.execute("INSERT OR IGNORE INTO profile_schemas VALUES(?,?,?,?)", (id, version, schema.id, schema.version))
            self.store.event("import-template", id, version)
        return profile

    def publish_template(self, library, id, version):
        profile = self.profile(id, version)
        library.publish(profile, self.schema(profile.schema_id, profile.schema_version))
        return profile

    def prepare_source(self, filename):
        return self.queue_source(copy_snapshot(filename, self.store.root))

    def queue_source(self, data):
        self.add_job("inspect", data, id="inspect-"+data["id"])
        return data["id"]

    def register_source(self, data, result):
        self._check_source_result(data["path"], data["sha256"], result)
        snapshot = source_from(data | {"pages": result["pages"]})
        if not snapshot.pages:
            raise RuleError("ページがありません")
        self.store.db.execute("INSERT INTO sources VALUES(?,?)", (snapshot.id, encode(asdict(snapshot))))
        self.store.event("source", snapshot.id)

    def register_profile(self, profile):
        profile.validate()
        with self.store.transaction():
            current = self.store.db.execute("SELECT MAX(version) FROM profiles WHERE id=?", (profile.id,)).fetchone()[0] or 0
            if profile.version != current + 1:
                raise RuleError("設定は次の版として登録してください。使用済みの版は上書きできません")
            if profile.schema_id:
                schema = self.schema(profile.schema_id, profile.schema_version)
                if schema.fields != profile.fields:
                    raise RuleError("テンプレートの項目と使用する項目定義が一致しません")
            else:
                # Compatibility for the v0.1.0 constructors. Never infer semantic identity from names.
                from .storage import legacy_schema_id
                schema = ResultSchema(legacy_schema_id(profile.id, profile.version), 1, profile.name, profile.fields)
                schema.validate()
                self.store.db.execute("INSERT INTO schemas VALUES(?,?,?)", (schema.id, schema.version, encode(asdict(schema))))
                profile = replace(profile, schema_id=schema.id, schema_version=schema.version)
            self.store.db.execute("INSERT INTO profiles(id,version,data) VALUES(?,?,?)", (profile.id, profile.version, encode(asdict(profile))))
            self.store.db.execute("INSERT INTO profile_schemas VALUES(?,?,?,?)", (profile.id, profile.version, schema.id, schema.version))
            self.store.event("profile", profile.id, profile.version)

    def apply_profile(self, source_id, profile_id, version):
        if self.profile(profile_id, version).scope != "document":
            raise RuleError("ページ用テンプレートは対象ページを指定して適用してください")
        mode = self.mode(source_id)
        if mode["mode"] is None:
            self.set_mode(source_id, "document", mode["revision"])
        if self.mode(source_id)["mode"] != "document":
            raise RuleError("この文書はページ単位で処理します")
        assignment = self.assignments(source_id)[0]
        if assignment.state != "unassigned":
            raise RuleError("文書には設定を適用済みです")
        return self.assign_pages(source_id, [0], profile_id, version, {0: assignment.revision})[0]

    def mode(self, source_id):
        self.source(source_id)
        row = self.store.db.execute("SELECT mode,revision FROM source_modes WHERE source_id=?", (source_id,)).fetchone()
        return dict(row) if row else {"mode": None, "revision": 0}

    def set_mode(self, source_id, mode, expected_revision=0):
        source = self.source(source_id)
        if mode not in ("document", "page"):
            raise RuleError("処理方式が不正です")
        with self.store.transaction():
            current = self.mode(source_id)
            if expected_revision != current["revision"]:
                raise StaleRevision("処理方式の古い版からの変更を拒否しました")
            if current["mode"] == mode:
                return current
            locked = self.store.db.execute("SELECT 1 FROM page_assignments WHERE source_id=? AND state!='unassigned' LIMIT 1", (source_id,)).fetchone()
            if locked:
                raise RuleError("テンプレート適用・対象外指定後は処理方式を変更できません")
            revision = current["revision"] + 1
            self.store.db.execute("INSERT INTO source_modes VALUES(?,?,?) ON CONFLICT(source_id) DO UPDATE SET mode=excluded.mode,revision=excluded.revision", (source_id, mode, revision))
            self.store.db.execute("DELETE FROM page_assignments WHERE source_id=?", (source_id,))
            pages = [0] if mode == "document" else range(1, len(source.pages)+1)
            self.store.db.executemany("INSERT INTO page_assignments VALUES(?,?,0,'unassigned',NULL,'')", [(source_id, p) for p in pages])
            self.store.event("mode", source_id, revision)
        return {"mode": mode, "revision": revision}

    def assignments(self, source_id):
        self.source(source_id)
        return [PageAssignment(**dict(r)) for r in self.store.db.execute("SELECT * FROM page_assignments WHERE source_id=? ORDER BY page", (source_id,))]

    def _targets(self, source_id, pages, expected_revisions):
        pages = list(dict.fromkeys(pages))
        if not pages or any(type(p) is not int for p in pages):
            raise RuleError("対象ページを選んでください")
        assignments = {a.page: a for a in self.assignments(source_id)}
        for page in pages:
            if page not in assignments:
                raise RuleError("対象ページがありません")
            if expected_revisions.get(page) != assignments[page].revision:
                raise StaleRevision("ページ割当の古い版からの変更を拒否しました")
        return [assignments[p] for p in sorted(pages)]

    def _retire_record(self, record_id):
        if record_id:
            self.store.db.execute("UPDATE records SET active=0 WHERE id=?", (record_id,))
            self.store.db.execute("UPDATE jobs SET status='cancelled',error='テンプレート変更・対象外指定により取消' WHERE kind='ocr' AND status IN ('pending','failed','running') AND json_extract(data,'$.record_id')=?", (record_id,))

    def assign_pages(self, source_id, pages, profile_id, version, expected_revisions):
        source, profile = self.source(source_id), self.profile(profile_id, version)
        mode = self.mode(source_id)["mode"]
        if mode != profile.scope:
            raise RuleError("文書用・ページ用の処理方式とテンプレートが一致しません")
        result = []
        with self.store.transaction():
            for assignment in self._targets(source_id, pages, expected_revisions):
                if assignment.current_record_id:
                    current = self.store.record(assignment.current_record_id)
                    if (current["profile_id"], current["profile_version"]) == (profile_id, version):
                        result.append(current["id"])
                        continue
                self._retire_record(assignment.current_record_id)
                actual_page = assignment.page or None
                matches = profile.matches(source, actual_page)
                fields = {}
                for f in profile.fields:
                    r = profile.resolve_region(f.id, actual_page)
                    anchor = Anchor(source.id, source.sha256, r["page"], tuple(r["rect"])) if matches else None
                    fields[f.id] = asdict(FieldState(unit=f.unit, anchor=anchor))
                id, revision = identifier(), assignment.revision+1
                self.store.db.execute("INSERT INTO records(id,source_id,profile_id,profile_version,revision,data,page,active,assignment_revision) VALUES(?,?,?,?,?,?,?,1,?)", (id, source_id, profile_id, version, 0, encode({"fields": fields, "geometry_matches": matches}), actual_page, revision))
                self.store.db.execute("UPDATE page_assignments SET revision=?,state='applied',current_record_id=?,reason='' WHERE source_id=? AND page=?", (revision, id, source_id, assignment.page))
                self.store.event("assign-page", id, revision)
                result.append(id)
        return result

    def exclude_pages(self, source_id, pages, reason, expected_revisions):
        if not isinstance(reason, str) or not reason.strip():
            raise RuleError("対象外にする理由を入力してください")
        with self.store.transaction():
            for a in self._targets(source_id, pages, expected_revisions):
                self._retire_record(a.current_record_id)
                self.store.db.execute("UPDATE page_assignments SET revision=?,state='excluded',current_record_id=NULL,reason=? WHERE source_id=? AND page=?", (a.revision+1, reason.strip(), source_id, a.page))
                self.store.event("exclude-page", source_id, a.revision+1)

    def history_records(self, source_id, page):
        column = "page IS NULL" if page == 0 else "page=?"
        args = (source_id,) if page == 0 else (source_id, page)
        return [self.store.record(r[0]) for r in self.store.db.execute("SELECT id FROM records WHERE source_id=? AND "+column+" ORDER BY rowid DESC", args)]

    def _active_context(self, record_id):
        record, source, profile = self.context(record_id)
        if not record["active"]:
            raise RuleError("変更前の記録は閲覧専用です")
        return record, source, profile

    def context(self, record_id):
        record = self.store.record(record_id)
        return record, self.source(record["source_id"]), self.profile(record["profile_id"], record["profile_version"])

    def edit(self, record_id, field_id, expected_revision, **changes):
        record, source, profile = self._active_context(record_id)
        if record["page"] is not None and changes.get("anchor") is not None and changes["anchor"].page != record["page"]:
            raise RuleError("ページ記録の根拠は対象ページに指定してください")
        schema = next(f for f in profile.fields if f.id == field_id)
        state = state_from(record["data"]["fields"][field_id])
        state.edit(schema, source=source, **changes)
        record["data"]["fields"][field_id] = asdict(state)
        with self.store.transaction():
            return self.store.update(record_id, expected_revision, record["data"])

    def accept(self, record_id, field_id, expected_revision, validation=None):
        record, source, profile = self._active_context(record_id)
        state = state_from(record["data"]["fields"][field_id])
        if record["page"] is not None and state.anchor is not None and state.anchor.page != record["page"]:
            raise RuleError("根拠ページが記録と一致しません")
        schema = next(f for f in profile.fields if f.id == field_id)
        state.accept(schema, source, expected_revision+1)
        record["data"]["fields"][field_id] = asdict(state)
        with self.store.transaction():
            # Validate fixed bytes as well as source identity before confirmation.
            proof = validation or validate_sources(self.store.root, [asdict(source)])
            if not isinstance(proof, ValidatedSources):
                raise RuleError("原本検証の結果が不正です")
            proof.check(self.store.root, [asdict(source)])
            return self.store.update(record_id, expected_revision, record["data"], "accept")

    def mark(self, record_id, field_id, expected_revision, status, reason):
        record, _, profile = self._active_context(record_id)
        state = state_from(record["data"]["fields"][field_id])
        state.mark(next(f for f in profile.fields if f.id == field_id), status, reason)
        record["data"]["fields"][field_id] = asdict(state)
        with self.store.transaction():
            return self.store.update(record_id, expected_revision, record["data"], "status")

    def adopt(self, record_id, candidate_id, expected_revision):
        row = self.store.db.execute("SELECT data FROM candidates WHERE id=? AND record_id=?", (candidate_id, record_id)).fetchone()
        if row is None:
            raise RuleError("候補がありません")
        c = json.loads(row[0])
        r, _, p = self.context(record_id)
        s = state_from(r["data"]["fields"][c["field_id"]])
        # A numeric transcription containing units needs explicit correction.
        return self.edit(record_id, c["field_id"], expected_revision, value=c["text"], unit=s.unit, raw=c["text"],
            anchor=Anchor(**(c["anchor"] | {"rect": tuple(c["anchor"]["rect"])})), candidate_id=c["id"])

    def candidates(self, record_id, field_id):
        return [json.loads(r[0]) for r in self.store.db.execute("SELECT data FROM candidates WHERE record_id=? ORDER BY rowid DESC", (record_id,))
            if json.loads(r[0])["field_id"] == field_id]

    def incomplete(self):
        result = []
        for row in self.store.rows("sources"):
            source = self.source(row["id"])
            assignments = self.assignments(source.id)
            if not assignments:
                result.append({"record_id": None, "source_id": source.id, "name": source.name,
                    "page": None, "kind": "unassigned", "reason": "処理方式・テンプレート未選択", "fields": ["設定未適用"]})
            for assignment in assignments:
                if assignment.state == "excluded":
                    continue
                fields, id = ["テンプレート未選択"], assignment.current_record_id
                if id:
                    r, _, p = self.context(id)
                    if not r["active"]:
                        raise RuleError("現在のページ割当が無効な記録を参照しています")
                    fields = unfinished(p, {k: state_from(v) for k, v in r["data"]["fields"].items()})
                if fields:
                    result.append({"record_id": id, "source_id": source.id, "name": source.name,
                        "page": assignment.page or None, "kind": "incomplete", "reason": "未完了", "fields": fields})
        for job in self.store.rows("jobs"):
            if job["kind"] == "inspect" and job["status"] != "complete":
                data = json.loads(job["data"])
                result.append({"record_id": None, "source_id": data["id"], "name": data["name"], "page": None,
                    "kind": "unregistered", "reason": "原本登録未完了", "fields": ["原本登録未完了"]})
        return result

    def finalize(self, *, completed_only=False, validation=None):
        incomplete = self.incomplete()
        if incomplete and not completed_only:
            raise RuleError("未完了の文書・ページがあります: " + "; ".join(r["name"]+(" p"+str(r["page"]) if r["page"] else "")+": "+", ".join(r["fields"]) for r in incomplete))
        excluded = list(incomplete)
        for row in self.store.rows("page_assignments"):
            if row["state"] == "excluded":
                source = self.source(row["source_id"])
                excluded.append({"record_id": None, "source_id": source.id, "name": source.name, "page": row["page"] or None,
                    "kind": "excluded", "reason": row["reason"], "fields": [row["reason"]]})
        groups = {}
        excluded_ids = {r["record_id"] for r in incomplete}
        with self.store.transaction():
            self.store.verify(validation)
            records = self.store.db.execute("SELECT r.id FROM records r JOIN sources s ON r.source_id=s.id WHERE r.active=1 ORDER BY s.rowid,COALESCE(r.page,0)").fetchall()
            for row in records:
                if row["id"] in excluded_ids:
                    continue
                record, source, profile = self.context(row["id"])
                states = {k: state_from(v) for k, v in record["data"]["fields"].items()}
                for f in profile.fields:
                    if states[f.id].status == Status.ACCEPTED:
                        if states[f.id].value != f.canonical(states[f.id].value):
                            raise RuleError("確認値が不正です")
                        states[f.id].anchor.validate(source)
                        if record["page"] is not None and states[f.id].anchor.page != record["page"]:
                            raise RuleError("根拠ページが記録と一致しません")
                schema = self.schema(profile.schema_id, profile.schema_version)
                key = (schema.id, schema.version)
                group = groups.setdefault(key, {"schema": asdict(schema), "profile": asdict(profile), "records": []})
                group["records"].append({"id": record["id"], "revision": record["revision"], "source": asdict(source),
                    "fields": record["data"]["fields"], "page": record["page"], "profile": asdict(profile),
                    "assignment_revision": record["assignment_revision"]})
            if not groups:
                raise RuleError("確認済みの記録がありません")
            dataset = FinalizedDataset(identifier(), timestamp(), tuple(groups.values()), tuple(excluded), format_version=2)
            self.store.db.execute("INSERT INTO datasets VALUES(?,?)", (dataset.id, encode(asdict(dataset))))
            self.store.event("finalize", dataset.id)
        return dataset.id

    def dataset(self, id):
        row = self.store.db.execute("SELECT data FROM datasets WHERE id=?", (id,)).fetchone()
        if row is None:
            raise RuleError("確定結果がありません")
        return json.loads(row[0])

    def add_job(self, kind, data, id=None):
        id = id or identifier()
        self.store.db.execute("INSERT OR IGNORE INTO jobs(id,kind,status,data) VALUES(?,?,?,?)", (id, kind, "pending", encode(data)))
        return id

    def render_job(self, source_id, page, dpi=150):
        s = self.source(source_id)
        if not 1 <= page <= len(s.pages) or dpi not in (150, 300):
            raise RuleError("描画ページ・解像度が不正です")
        id = self.add_job("render", {"source_id": s.id, "sha256": s.sha256, "path": s.path, "page": page, "dpi": dpi,
            "image": f"cache/{s.id}/page-{page}-{dpi}.png"}, id=f"render-{s.id}-{page}-{dpi}")
        image = self.store.path(f"cache/{s.id}/page-{page}-{dpi}.png")
        job = self.job(id)
        result = json.loads(job["result"]) if job["result"] else {}
        if not image.is_file() or job["status"] == "complete" and result.get("image_sha256") != digest(image):
            self.store.db.execute("UPDATE jobs SET status='pending' WHERE id=?", (id,))
        return id

    def ocr_jobs(self, record_id):
        record, source, profile = self._active_context(record_id)
        if not profile.matches(source, record["page"]):
            raise RuleError("ページ数・寸法・向きが設定と不一致です。手入力と文書固有の範囲指定をご利用ください")
        run = identifier()
        jobs = []
        for f in profile.fields:
            r = profile.resolve_region(f.id, record["page"])
            self.render_job(source.id, r["page"], 300)
            jobs.append(self.add_job("ocr", {"run": run, "record_id": record_id, "field_id": f.id, "source_id": source.id,
                "sha256": source.sha256, "profile_id": profile.id, "profile_version": profile.version,
                "assignment_revision": record["assignment_revision"], "page": r["page"],
                "rect": r["rect"], "image": f"cache/{source.id}/page-{r['page']}-300.png"}))
        return jobs

    def pending_jobs(self):
        # Render tasks precede their OCR consumers. Failed tasks are retried only on explicit resume.
        prepared = set()
        for row in self.store.db.execute("SELECT id,data FROM jobs WHERE kind='ocr' AND status IN ('pending','failed')").fetchall():
            data = json.loads(row["data"])
            if not self._job_current(data):
                self.store.db.execute("UPDATE jobs SET status='cancelled',error='現在のページ割当ではありません' WHERE id=?", (row["id"],))
                continue
            key = (data["source_id"], data["page"])
            if key not in prepared:
                self.render_job(*key, 300)
                prepared.add(key)
        rows = [r for r in self.store.rows("jobs") if r["status"] in ("pending", "failed")]
        return sorted(rows, key=lambda r: {"inspect": 0, "render": 1, "ocr": 2}[r["kind"]])

    def job(self, id):
        r = dict(self.store.db.execute("SELECT * FROM jobs WHERE id=?", (id,)).fetchone())
        r["data"] = json.loads(r["data"])
        return r

    def start_job(self, id):
        job = self.job(id)
        if job["status"] in ("complete", "cancelled"):
            return None
        if job["kind"] == "ocr" and not self._job_current(job["data"]):
            self.store.db.execute("UPDATE jobs SET status='cancelled',error='現在のページ割当ではありません' WHERE id=?", (id,))
            return None
        self.store.db.execute("UPDATE jobs SET status='running',error=NULL WHERE id=?", (id,))
        return job

    def finish_job(self, id, result=None, error=None):
        job = self.job(id)
        if job["status"] in ("complete", "cancelled"):
            return
        data = job["data"]
        with self.store.transaction():
            if job["kind"] == "ocr" and not self._job_current(data):
                self.store.db.execute("UPDATE jobs SET status='cancelled',error='現在のページ割当ではありません' WHERE id=?", (id,))
                self.store.event("job-cancelled", id)
                return
            if error is None:
                if job["kind"] == "inspect":
                    self.register_source(data, result)
                elif job["kind"] == "ocr":
                    self._save_ocr(id, data, result)
                elif job["kind"] == "render":
                    self._check_source_result(data["path"], data["sha256"], result)
                    if not self.store.path(data["image"]).is_file():
                        raise RuleError("描画ファイルがありません")
                    if digest(self.store.path(data["image"])) != result["image_sha256"]:
                        raise RuleError("描画ファイルが保存前に変わりました")
                self.store.db.execute("UPDATE jobs SET status='complete',result=?,error=NULL WHERE id=?", (encode(result), id))
            else:
                self.store.db.execute("UPDATE jobs SET status='failed',error=? WHERE id=?", (str(error), id))
            self.store.event("job-" + ("failed" if error else "complete"), id)

    def _job_current(self, data):
        try:
            record = self.store.record(data["record_id"])
        except RuleError:
            return False
        if record["page"] is not None and data.get("page") != record["page"]:
            return False
        profile = self.profile(record["profile_id"], record["profile_version"])
        if data.get("field_id") not in {f.id for f in profile.fields}:
            return False
        assignment = self.store.db.execute("SELECT current_record_id,revision FROM page_assignments WHERE source_id=? AND page=?", (record["source_id"], record["page"] or 0)).fetchone()
        return bool(record["active"] and assignment and assignment["current_record_id"] == record["id"] and
            assignment["revision"] == data.get("assignment_revision", record["assignment_revision"]))

    def _save_ocr(self, job_id, data, result):
        record, source, profile = self._active_context(data["record_id"])
        if (source.id, source.sha256, profile.id, profile.version) != (data["source_id"], data["sha256"], data["profile_id"], data["profile_version"]):
            raise RuleError("OCRの原本・設定が一致しません")
        self._check_source_result(source.path, source.sha256, result)
        anchor = Anchor(source.id, source.sha256, data["page"], tuple(data["rect"]))
        anchor.validate(source)
        ids = []
        for i, row in enumerate(result["regions"]):
            obs = Observation(job_id+"-"+str(i), source.id, source.sha256, data["field_id"], anchor, row["text"], row["confidence"],
                result["engine"], tuple(tuple(p) for p in row["polygon_mm"]))
            self.store.db.execute("INSERT INTO observations VALUES(?,?,?)", (obs.id, record["id"], encode(asdict(obs))))
            ids.append(obs.id)
        if ids:
            candidate = Candidate(job_id, data["field_id"], result["text"], anchor, tuple(ids))
            self.store.db.execute("INSERT INTO candidates VALUES(?,?,?)", (candidate.id, record["id"], encode(asdict(candidate))))
        # No machine operation changes adopted values, review status or human revision.

    def _check_source_result(self, path, sha256, result):
        current = self.store.path(path)
        if "source_fingerprint" in result:
            valid = result["source_hash"] == sha256 and tuple(result["source_fingerprint"]) == fingerprint(current)
        else:
            valid = digest(current) == sha256
        if not valid:
            raise RuleError("処理後に固定原本が変わりました")

    def worker_request(self, job, portable_root):
        data = dict(job["data"])
        if job["kind"] in ("inspect", "render"):
            # The native worker validates bytes before and after its read-only SDK call.
            data["path"] = str(self.store.path(data["path"]))
        if job["kind"] == "render":
            data["image"] = str(self.store.path(data["image"]))
        if job["kind"] == "ocr":
            source = self.source(data["source_id"])
            data["source_path"] = str(self.store.path(source.path))
            render = self.job(f"render-{source.id}-{data['page']}-300")
            if render["status"] != "complete" or json.loads(render["result"])["image_sha256"] != digest(self.store.path(data["image"])):
                raise RuleError("範囲OCRのページ画像が未完成または破損しています。描画から再開してください")
            data["page_info"] = asdict(source.pages[data["page"]-1])
            data["image"] = str(self.store.path(data["image"]))
            data["models"] = str(Path(portable_root)/"models")
            data["cache"] = str(self.store.path("cache/ocr"))
        data["temp"] = str(self.store.path("staging/worker-"+job["id"]))
        return {"kind": job["kind"], "data": data}

    def export(self, dataset_id, formats=("xlsx", "csv")):
        from .exporting import export_dataset
        return export_dataset(self.store, self.dataset(dataset_id), formats)

    def close(self):
        self.store.close()
