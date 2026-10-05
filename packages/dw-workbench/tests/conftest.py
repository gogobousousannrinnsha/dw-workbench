import sys
from pathlib import Path
import uuid
import os
import tempfile
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def workdir():
    # Normal mkdir inherits the Windows ACL; do not use Python's 0700 temp helper.
    root = Path(os.environ.get("DW_WORKBENCH_TEST_TMP", str(Path(tempfile.gettempdir())/"workbench-tests")))/uuid.uuid4().hex
    root.mkdir(parents=True)
    return root


@pytest.fixture
def app(workdir):
    from dw_workbench.application import Workbench
    result = Workbench(workdir/"案件 日本語")
    yield result
    result.close()


@pytest.fixture
def sample(app, workdir):
    from dw_workbench.domain import ExtractionProfile, PageInfo, FieldSchema, identifier
    path = workdir/"fixture.xdw"
    path.write_bytes(b"Unit fixture, NOT a runtime-valid XDW")
    id = app.prepare_source(path)
    job = app.job("inspect-"+id)
    app.finish_job(job["id"], {"pages": [{"width_mm": 210, "height_mm": 297, "rotation": 0}]})
    profile = ExtractionProfile(identifier(), 1, "Test", (PageInfo(210, 297),),
        (FieldSchema("part", "部品番号"), FieldSchema("temp", "温度", "decimal", True, "℃"), FieldSchema("note", "備考", required=False)),
        {"part": {"page": 1, "rect": [10, 20, 30, 8]}, "temp": {"page": 1, "rect": [10, 40, 30, 8]}, "note": {"page": 1, "rect": [10, 60, 30, 8]}})
    app.register_profile(profile)
    record = app.apply_profile(id, profile.id, 1)
    return id, profile, record


def complete(app, record):
    from dw_workbench.domain import state_from, Status
    for field, value in (("part", "001234"), ("temp", "２５.０")):
        r = app.store.record(record)
        state = state_from(r["data"]["fields"][field])
        app.edit(record, field, r["revision"], value=value, unit=state.unit, raw=value, anchor=state.anchor)
        app.accept(record, field, app.store.record(record)["revision"])
    app.mark(record, "note", app.store.record(record)["revision"], Status.NOT_APPLICABLE, "記載なし")
