from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from docuworks_ctypes import PointMM, RectMM

from .models import PixelPoint, PixelRect


@dataclass(frozen=True, slots=True)
class PageTransform:
    pixel_width: int
    pixel_height: int
    page_width_mm: float
    page_height_mm: float

    def __post_init__(self) -> None:
        if isinstance(self.pixel_width, bool) or not isinstance(self.pixel_width, int):
            raise TypeError("pixel_width must be int")
        if isinstance(self.pixel_height, bool) or not isinstance(self.pixel_height, int):
            raise TypeError("pixel_height must be int")
        if self.pixel_width <= 0 or self.pixel_height <= 0:
            raise ValueError("pixel dimensions must be positive")
        for name in ("page_width_mm", "page_height_mm"):
            value = float(getattr(self, name))
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive and finite")
            object.__setattr__(self, name, value)

    @property
    def scale_x(self) -> float:
        return self.page_width_mm / self.pixel_width

    @property
    def scale_y(self) -> float:
        return self.page_height_mm / self.pixel_height

    def validate_rect(self, rect: PixelRect) -> None:
        if not isinstance(rect, PixelRect):
            raise TypeError("rect must be PixelRect")
        if rect.right > self.pixel_width or rect.bottom > self.pixel_height:
            raise ValueError("pixel rectangle extends outside the image")

    def point_to_mm(self, point: PixelPoint) -> PointMM:
        if not isinstance(point, PixelPoint):
            raise TypeError("point must be PixelPoint")
        if point.x < 0 or point.y < 0 or point.x > self.pixel_width or point.y > self.pixel_height:
            raise ValueError("pixel point is outside the image")
        return PointMM(point.x * self.scale_x, point.y * self.scale_y)

    def rect_to_mm(self, rect: PixelRect) -> RectMM:
        self.validate_rect(rect)
        return RectMM(
            rect.x * self.scale_x,
            rect.y * self.scale_y,
            rect.width * self.scale_x,
            rect.height * self.scale_y,
        )
