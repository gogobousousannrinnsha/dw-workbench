"""Verify real v1 project copies with the installed v0.2.0 application.

Original cases remain unchanged. Deliberately damaged exports belong to copies.
"""
import argparse
import json
from pathlib import Path
import time
import traceback

import dw_workbench
from dw_workbench.application import Workbench
from dw_workbench.storage import digest, readonly_database, migrate_project_copy


def inventory(root):
    files = {"project.sqlite": digest(root/"project.sqlite")}
    for directory in ("sources", "exports", "drafts"):
        for path in (root/directory).rglob("*"):
            if path.is_file():
                files[path.relative_to(root).as_posix()] = digest(path)
    db = readonly_database(root/"project.sqlite")
    try:
        tables = ("sources", "profiles", "records", "observations", "candidates", "jobs", "datasets", "artifacts", "events")
        counts = {table: db.execute("SELECT COUNT(*) FROM "+table).fetchone()[0] for table in tables}
        payloads = {table: dict(db.execute("SELECT id,data FROM "+table))
            for table in ("sources", "records", "observations", "candidates", "jobs", "datasets")}
        payloads["profiles"] = {f"{row[0]}:{row[1]}": row[2] for row in db.execute("SELECT id,version,data FROM profiles")}
        return {"files": files, "counts": counts, "payloads": payloads, "format": db.execute("PRAGMA user_version").fetchone()[0]}
    finally:
        db.close()


def verify(args, report):
    portable = args.portable.resolve()
    if not Path(dw_workbench.__file__).resolve().is_relative_to(portable/"runtime"):
        raise RuntimeError("Use the final Portable runtime/python.exe -I without a source override")
    report.update({"package_file": dw_workbench.__file__, "version": dw_workbench.__version__,
        "build": json.loads((portable/"BUILD.json").read_text(encoding="utf-8")),
        "installed_source_sha256": {name: digest(Path(dw_workbench.__file__).parent/name)
            for name in ("domain.py", "storage.py", "library.py", "application.py", "exporting.py")}})
    names = args.project_name or ["自動検証 合成帳票", "自動検証 100文書"]
    for name in names:
        original = args.old_portable.resolve()/"projects"/name
        before = inventory(original)
        start = time.perf_counter()
        clone = migrate_project_copy(original, portable/"projects")
        migrated = inventory(clone)
        assert before["format"] == 1 and migrated["format"] == 2
        assert before["payloads"] == migrated["payloads"], "Migration changed original JSON data"
        assert before["counts"] == migrated["counts"], "Migration changed legacy row counts"
        assert all(before["files"][path] == migrated["files"][path]
            for path in before["files"] if path != "project.sqlite")
        app = Workbench(clone)
        try:
            assert app.store.verify()
            datasets = app.store.rows("datasets")
            historic_retry = []
            if datasets:
                first = datasets[0]["id"]
                frozen = app.dataset(first)
                assert frozen.get("format_version", 1) == 1
                historic_files = [row for row in app.store.rows("artifacts")
                    if row["dataset_id"] == first and row["status"] == "complete"]
                for row in historic_files:
                    app.store.path(row["path"]).write_bytes(b"Damaged verification-copy export for v1 retry")
                historic_retry = app.export(first)
                assert historic_retry and all(row["status"] == "complete" for row in historic_retry), historic_retry
                assert app.dataset(first) == frozen
            new_id = app.finalize(completed_only=bool(app.incomplete()))
            snapshot = app.dataset(new_id)
            assert snapshot["format_version"] == 2
            new_artifacts = app.export(new_id)
            assert new_artifacts and all(row["status"] == "complete" for row in new_artifacts), new_artifacts
            record_count = sum(len(group["records"]) for group in snapshot["groups"])
            field_count = sum(len(record["fields"]) for group in snapshot["groups"] for record in group["records"])
            assert app.store.verify()
            outcome = {"original": str(original), "migrated": str(clone), "legacy_counts": before["counts"],
                "original_file_hashes": before["files"], "legacy_json_unchanged": True,
                "copied_sources_exports_drafts_hashes_match": True, "historical_v1_retry": historic_retry,
                "new_dataset": new_id, "format_version": 2, "new_record_count": record_count,
                "new_field_count": field_count, "new_artifacts": new_artifacts,
                "excluded_count": len(snapshot["excluded"]), "seconds": round(time.perf_counter()-start, 3)}
        finally:
            app.close()
        assert inventory(original) == before, "Old Portable project was changed"
        outcome["original_database_sources_exports_drafts_unchanged"] = True
        report["projects"].append(outcome)
        print(json.dumps({"project": name, "records": record_count, "fields": field_count,
            "seconds": outcome["seconds"], "old_unchanged": True}, ensure_ascii=False), flush=True)
    report["status"] = "passed"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-portable", required=True, type=Path)
    parser.add_argument("--portable", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--project-name", action="append")
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    report = {"status": "running", "code_provenance": "final installed Portable", "projects": []}
    try:
        verify(args, report)
    except BaseException:
        report.update(status="failed", error=traceback.format_exc())
        raise
    finally:
        (args.evidence/"verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
