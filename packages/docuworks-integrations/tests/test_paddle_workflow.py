import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from docuworks_integrations import OcrRegion, PixelRect, PageTransform, build_marker_plan
from docuworks_integrations.paddle import parse_paddle_result
from docuworks_integrations.workflow import ocr_xdw, mark_region, sha256, write_json, verify_run
import docuworks_integrations.workflow as workflow
import docuworks_integrations.executor as executor


def result():
    return {"rec_texts": ["A-101", "SUS3O4"], "rec_scores": [.9, .6],
            "rec_polys": [[[10, 10], [60, 10], [60, 20], [10, 20]],
                          [[10, 30], [70, 30], [70, 40], [10, 40]]],
            "dt_polys": [[[0, 0], [1, 0], [1, 1], [0, 1]]]}


def test_ocr_uses_rec_polys_and_preserves_text():
    regions = parse_paddle_result(result(), 100, 100)
    assert regions[1].text == "SUS3O4"
    assert regions[0].bbox == PixelRect(10, 10, 50, 10)
    assert len(regions[0].polygon) == 4


@pytest.mark.parametrize("change", ["length", "nan", "outside", "nonstring", "area"])
def test_ocr_invalid_output_rejected(change):
    data = result()
    if change == "length": data["rec_scores"].pop()
    if change == "nan": data["rec_scores"][0] = float("nan")
    if change == "outside": data["rec_polys"][0][0][0] = -1
    if change == "nonstring": data["rec_texts"][0] = None
    if change == "area": data["rec_polys"][0] = [[10, 10]] * 4
    with pytest.raises(ValueError): parse_paddle_result(data, 100, 100)


def test_marker_geometry_rounding_and_single_operation(tmp_path):
    region = OcrRegion("品番", PixelRect(100, 200, 200, 50), .9)
    plan = build_marker_plan(tmp_path / "page.png", region, PageTransform(1000, 1000, 100, 100))
    assert len(plan.operations) == 1
    marker = plan.operations[0]
    assert [(p.x, p.y) for p in marker.points] == [(10, 22.5), (30, 22.5)]
    assert marker.border_width == 14
    assert marker.border_transparent is True
    assert plan.to_dict()["operations"][0]["kind"] == "marker"


def fake_render(source, root, page, dpi, dll_path):
    from PIL import Image
    (root / "source.xdw").write_bytes(source.read_bytes())
    Image.new("RGB", (100, 100), "white").save(root / "page.png")
    return {"source_path": str(source), "source_sha256": sha256(source), "page": 1,
            "pixel_width": 100, "pixel_height": 100, "page_width_mm": 100, "page_height_mm": 100,
            "dll_path": "unused"}


def make_run(monkeypatch, tmp_path):
    source = tmp_path / "原本.xdw"
    source.write_bytes(b"original")
    root = tmp_path / "run"
    monkeypatch.setattr(workflow, "render_page", fake_render)
    engine = SimpleNamespace(last_raw=result(), recognize=lambda path: parse_paddle_result(result(), 100, 100))
    ocr_xdw(source, root, tmp_path, engine=engine)
    return source, root


def test_preview_roundtrip_and_dry_run(monkeypatch, tmp_path):
    source, root = make_run(monkeypatch, tmp_path)
    assert (root / "preview.png").is_file()
    monkeypatch.setattr(executor, "open_xdw", lambda *a, **k: pytest.fail("DLL used by dry-run"))
    before = {p.name: sha256(p) for p in root.iterdir()}
    report = mark_region(root, 2, tmp_path / "out.xdw", dry_run=True)
    assert report["text"] == "SUS3O4"
    assert report["execution"]["executed_operations"] == 0
    assert {p.name: sha256(p) for p in root.iterdir()} == before
    assert source.read_bytes() == b"original"


@pytest.mark.parametrize("name", ["page.png", "regions.json", "source.xdw", "preview.png", "original"])
def test_changed_preview_input_blocks_marking(monkeypatch, tmp_path, name):
    source, root = make_run(monkeypatch, tmp_path)
    path = source if name == "original" else root / name
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(RuntimeError, match="changed"):
        mark_region(root, 1, tmp_path / "out.xdw")
    assert not (tmp_path / "out.xdw").exists()


@pytest.mark.parametrize("number", [0, -1, 3, True])
def test_invalid_selection(monkeypatch, tmp_path, number):
    _, root = make_run(monkeypatch, tmp_path)
    with pytest.raises(ValueError): mark_region(root, number, tmp_path / "out.xdw", dry_run=True)


@pytest.mark.parametrize("failure", ["empty", "gpu"])
def test_ocr_failure_keeps_diagnostic_and_no_completed_run(monkeypatch, tmp_path, failure):
    source = tmp_path / "source.xdw"
    source.write_bytes(b"original")
    monkeypatch.setattr(workflow, "render_page", fake_render)
    def recognize(path):
        if failure == "gpu": raise RuntimeError("GPU failure")
        return ()
    with pytest.raises((ValueError, RuntimeError)):
        ocr_xdw(source, tmp_path / "run", tmp_path, engine=SimpleNamespace(recognize=recognize, last_raw={}))
    assert (tmp_path / "run" / "error.json").is_file()
    assert not (tmp_path / "run" / "run.json").exists()
    assert source.read_bytes() == b"original"


@pytest.mark.parametrize("bad", [None, "points", "%BorderWidth", "%BorderColor", "%BorderTransparent"])
def test_marker_readback_uses_absolute_points(bad):
    from docuworks_ctypes import PointMM
    from docuworks_integrations.models import AddMarker
    operation = AddMarker((PointMM(20, 30), PointMM(40, 30)), 12)
    attrs = {"%Points": operation.points, "%BorderWidth": 12, "%BorderColor": int(operation.border_color), "%BorderTransparent": True}
    if bad == "points": attrs["%Points"] = (PointMM(20, 30), PointMM(40.02, 30))
    elif bad is not None: attrs[bad] = -1
    annotation = SimpleNamespace(position=PointMM(17.5, 27.5), core=SimpleNamespace(get_standard_attribute=lambda key: attrs[key]))
    if bad is None:
        executor.verify_marker(annotation, operation)
    else:
        with pytest.raises(RuntimeError): executor.verify_marker(annotation, operation)
