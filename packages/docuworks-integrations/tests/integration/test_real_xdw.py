from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from docuworks_ctypes import AnnotationType
from docuworks_ctypes.simple import open_xdw
from docuworks_integrations import JsonOcrEngine, PageTransform, build_ocr_plan, execute_plan
from docuworks_integrations.opencv import read_image_size


pytestmark = pytest.mark.integration


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def test_png_json_to_rectangle_text_save_reopen(tmp_path):
    fixture_value = os.environ.get("DOCUWORKS_TEST_XDW")
    if not fixture_value:
        pytest.skip("DOCUWORKS_TEST_XDW is required")
    fixture = Path(fixture_value).resolve()
    before = _hash(fixture)
    cv2 = pytest.importorskip("cv2")
    numpy = pytest.importorskip("numpy")
    image = tmp_path / "page.png"
    pixels = numpy.full((1000, 1000, 3), 255, dtype=numpy.uint8)
    cv2.rectangle(pixels, (100, 200), (400, 300), (0, 0, 0), 2)
    assert cv2.imwrite(str(image), pixels)
    regions = tmp_path / "regions.json"
    regions.write_text(
        json.dumps([{"text": "A-101", "bbox": {"x": 100, "y": 200, "width": 300, "height": 100}, "confidence": 0.99}]),
        encoding="utf-8",
    )
    width, height = read_image_size(image)
    plan = build_ocr_plan(image, JsonOcrEngine(regions), PageTransform(width, height, 210, 297))
    output = tmp_path / "annotated.xdw"
    report = execute_plan(plan, fixture, output)
    assert report.status == "VERIFIED"
    assert report.executed_operations == 2
    assert report.input_sha256_before == report.input_sha256_after == before
    assert _hash(fixture) == before
    with open_xdw(output) as document:
        tail = document.page(1).annotations()[-2:]
        assert tuple(item.type for item in tail) == (AnnotationType.RECTANGLE, AnnotationType.TEXT)
        assert tail[1].core.get_standard_attribute("%Text") == "A-101"
        assert tail[0].position.x == pytest.approx(21.0, abs=0.01)
        assert tail[0].position.y == pytest.approx(59.4, abs=0.01)
