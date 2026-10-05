from __future__ import annotations

import math

import pytest

from docuworks_integrations import OcrRegion, PageTransform, PixelPoint, PixelRect


def test_non_square_pixel_to_mm_transform_and_edges():
    transform = PageTransform(1000, 500, 200, 200)
    assert transform.point_to_mm(PixelPoint(500, 250)).x == 100
    assert transform.point_to_mm(PixelPoint(500, 250)).y == 100
    rect = transform.rect_to_mm(PixelRect(100, 50, 200, 100))
    assert (rect.x, rect.y, rect.width, rect.height) == (20, 20, 40, 40)
    transform.validate_rect(PixelRect(999, 499, 1, 1))


@pytest.mark.parametrize(
    "factory",
    [
        lambda: PageTransform(0, 1, 1, 1),
        lambda: PageTransform(1, 1, math.inf, 1),
        lambda: PixelRect(-1, 0, 1, 1),
        lambda: PixelRect(0, 0, 0, 1),
        lambda: OcrRegion("", PixelRect(0, 0, 1, 1)),
        lambda: OcrRegion("text", PixelRect(0, 0, 1, 1), 1.1),
    ],
)
def test_invalid_model_values_are_rejected(factory):
    with pytest.raises((TypeError, ValueError)):
        factory()


def test_out_of_bounds_geometry_is_rejected():
    transform = PageTransform(100, 100, 210, 297)
    with pytest.raises(ValueError, match="outside"):
        transform.rect_to_mm(PixelRect(90, 90, 11, 10))
    with pytest.raises(ValueError, match="outside"):
        transform.point_to_mm(PixelPoint(101, 50))
