from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .models import PixelRect


def _cv2() -> Any:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError(
            "OpenCV support requires: pip install docuworks-integrations[opencv]"
        ) from exc
    return cv2


def read_image_size(path: str | Path) -> tuple[int, int]:
    image_path = Path(path).expanduser().resolve()
    image = _cv2().imread(str(image_path), _cv2().IMREAD_UNCHANGED)
    if image is None or getattr(image, "ndim", 0) < 2:
        raise ValueError(f"OpenCV could not decode image: {image_path}")
    height, width = image.shape[:2]
    if width <= 0 or height <= 0:
        raise ValueError("decoded image has invalid dimensions")
    return int(width), int(height)


def bounding_rects(contours: Iterable[Any]) -> tuple[PixelRect, ...]:
    cv2 = _cv2()
    return tuple(PixelRect(*map(float, cv2.boundingRect(contour))) for contour in contours)


def find_contour_rects(
    path: str | Path, *, threshold: int = 127, min_area: float = 1.0
) -> tuple[PixelRect, ...]:
    if isinstance(threshold, bool) or not isinstance(threshold, int) or not 0 <= threshold <= 255:
        raise ValueError("threshold must be an integer from 0 through 255")
    if min_area <= 0:
        raise ValueError("min_area must be positive")
    cv2 = _cv2()
    image_path = Path(path).expanduser().resolve()
    gray = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError(f"OpenCV could not decode image: {image_path}")
    _, binary = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    selected = [contour for contour in contours if float(cv2.contourArea(contour)) >= min_area]
    return tuple(sorted(bounding_rects(selected), key=lambda rect: (rect.y, rect.x)))
