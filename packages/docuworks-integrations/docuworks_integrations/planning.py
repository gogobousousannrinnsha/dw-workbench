from __future__ import annotations

from pathlib import Path

from docuworks_ctypes import PointMM

from .models import AddRectangle, AddText, AddMarker, AnnotationPlan, PixelPoint, OcrRegion
from .ocr import OcrEngine
from .transforms import PageTransform


def build_marker_plan(image_path: str | Path, region: OcrRegion, transform: PageTransform, *, page: int = 1) -> AnnotationPlan:
    from math import floor
    transform.validate_rect(region.bbox)
    rect = transform.rect_to_mm(region.bbox)
    points = (PointMM(rect.x, rect.y + rect.height / 2), PointMM(rect.x + rect.width, rect.y + rect.height / 2))
    width = max(1, floor(rect.height * 72 / 25.4 + 0.5))
    return AnnotationPlan(Path(image_path), page, transform.pixel_width, transform.pixel_height,
                          transform.page_width_mm, transform.page_height_mm, (region,), (AddMarker(points, width),))


def build_ocr_plan(
    image_path: str | Path,
    engine: OcrEngine,
    transform: PageTransform,
    *,
    page: int = 1,
    confidence_threshold: float = 0.0,
    font_size: float = 12.0,
) -> AnnotationPlan:
    path = Path(image_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    threshold = float(confidence_threshold)
    if threshold < 0 or threshold > 1:
        raise ValueError("confidence_threshold must be between 0 and 1")
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValueError("page must be a positive one-based integer")
    accepted = []
    operations = []
    for region in engine.recognize(path):
        transform.validate_rect(region.bbox)
        if region.confidence is not None and region.confidence < threshold:
            continue
        rect = transform.rect_to_mm(region.bbox)
        position = transform.point_to_mm(PixelPoint(region.bbox.x, region.bbox.y))
        accepted.append(region)
        operations.extend((AddRectangle(rect), AddText(region.text, PointMM(position.x, position.y), font_size)))
    return AnnotationPlan(
        image_path=path,
        page=page,
        pixel_width=transform.pixel_width,
        pixel_height=transform.pixel_height,
        page_width_mm=transform.page_width_mm,
        page_height_mm=transform.page_height_mm,
        regions=tuple(accepted),
        operations=tuple(operations),
    )
