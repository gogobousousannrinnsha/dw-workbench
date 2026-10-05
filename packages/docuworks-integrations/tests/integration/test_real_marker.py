import os
from pathlib import Path

import pytest

from docuworks_ctypes import AnnotationType
from docuworks_ctypes.simple import open_xdw
from docuworks_integrations import OcrRegion, PixelRect, PageTransform, build_marker_plan, execute_plan
from docuworks_integrations.workflow import render_page, sha256

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("precommit_failure", [False, True])
def test_render_and_marker_copy_save_reopen(tmp_path, precommit_failure):
    value = os.environ.get("DOCUWORKS_TEST_XDW")
    if not value:
        pytest.skip("DOCUWORKS_TEST_XDW is required")
    source = Path(value)
    before = sha256(source)
    meta = render_page(source, tmp_path, 1, 300, r"C:\Windows\System32\xdwapi.dll")
    assert meta["pixel_width"] > 0
    region = OcrRegion("contract", PixelRect(100, 200, 200, 50), .99)
    transform = PageTransform(meta["pixel_width"], meta["pixel_height"], meta["page_width_mm"], meta["page_height_mm"])
    plan = build_marker_plan(tmp_path / "page.png", region, transform)
    output = tmp_path / "marked.xdw"
    def fail():
        raise RuntimeError("input changed before commit")
    if precommit_failure:
        with pytest.raises(RuntimeError, match="before commit"):
            execute_plan(plan, tmp_path / "source.xdw", output, precommit_check=fail)
        assert not output.exists()
        assert not list(tmp_path.glob(".docuworks-integrations-*"))
    else:
        report = execute_plan(plan, tmp_path / "source.xdw", output)
        assert report.verified
        assert report.annotations_after == report.annotations_before + 1
        with open_xdw(output) as document:
            annotation = document.page(1).annotations()[-1]
            assert annotation.type == AnnotationType.MARKER
            points = annotation.core.get_standard_attribute("%Points")
            for point, expected in zip(points, plan.operations[0].points):
                assert point.x == pytest.approx(expected.x, abs=.01)
                assert point.y == pytest.approx(expected.y, abs=.01)
    assert sha256(source) == before
