from __future__ import annotations

import json

import pytest

from docuworks_integrations import (
    AddRectangle,
    AddText,
    JsonOcrEngine,
    PageTransform,
    build_ocr_plan,
)


def test_json_ocr_plan_is_rectangle_then_text(tmp_path):
    image = tmp_path / "page.png"
    image.write_bytes(b"image")
    regions = tmp_path / "regions.json"
    regions.write_text(
        json.dumps(
            {
                "regions": [
                    {"text": "A-101", "bbox": {"x": 10, "y": 20, "width": 30, "height": 10}, "confidence": 0.9},
                    {"text": "low", "bbox": {"x": 1, "y": 1, "width": 2, "height": 2}, "confidence": 0.1},
                ]
            }
        ),
        encoding="utf-8",
    )
    plan = build_ocr_plan(
        image,
        JsonOcrEngine(regions),
        PageTransform(100, 100, 200, 300),
        confidence_threshold=0.5,
    )
    assert len(plan.regions) == 1
    assert isinstance(plan.operations[0], AddRectangle)
    assert isinstance(plan.operations[1], AddText)
    assert plan.operations[0].rect.x == 20
    assert plan.operations[0].rect.y == 60
    assert plan.operations[1].text == "A-101"
    assert plan.to_dict()["operations"][0]["kind"] == "rectangle"


def test_invalid_json_and_threshold_are_rejected(tmp_path):
    image = tmp_path / "page.png"
    image.write_bytes(b"image")
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        JsonOcrEngine(bad).recognize(image)
    with pytest.raises(ValueError):
        build_ocr_plan(image, JsonOcrEngine(bad), PageTransform(1, 1, 1, 1), confidence_threshold=2)
