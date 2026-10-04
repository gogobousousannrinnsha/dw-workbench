from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from pathlib import Path
from typing import Any, Literal

from docuworks_ctypes import PointMM, RectMM, Color


def _finite(name: str, value: float) -> float:
    converted = float(value)
    if not isfinite(converted):
        raise ValueError(f"{name} must be finite")
    return converted


@dataclass(frozen=True, slots=True)
class PixelPoint:
    x: float
    y: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _finite("x", self.x))
        object.__setattr__(self, "y", _finite("y", self.y))


@dataclass(frozen=True, slots=True)
class PixelRect:
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        for name in ("x", "y", "width", "height"):
            object.__setattr__(self, name, _finite(name, getattr(self, name)))
        if self.x < 0 or self.y < 0:
            raise ValueError("pixel rectangle origin must be non-negative")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("pixel rectangle width and height must be positive")

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


@dataclass(frozen=True, slots=True)
class OcrRegion:
    text: str
    bbox: PixelRect
    confidence: float | None = None
    polygon: tuple[PixelPoint, ...] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("OCR text must be a non-empty string")
        if not isinstance(self.bbox, PixelRect):
            raise TypeError("bbox must be PixelRect")
        if self.polygon is not None:
            points = tuple(self.polygon)
            if len(points) != 4 or not all(isinstance(p, PixelPoint) for p in points):
                raise ValueError("polygon requires four PixelPoint values")
            object.__setattr__(self, "polygon", points)
        if self.confidence is not None:
            value = _finite("confidence", self.confidence)
            if value < 0 or value > 1:
                raise ValueError("confidence must be between 0 and 1")
            object.__setattr__(self, "confidence", value)


@dataclass(frozen=True, slots=True)
class AddRectangle:
    rect: RectMM
    kind: Literal["rectangle"] = "rectangle"


@dataclass(frozen=True, slots=True)
class AddText:
    text: str
    position: PointMM
    font_size: float = 12.0
    kind: Literal["text"] = "text"

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("text operation requires non-empty text")
        if not isfinite(float(self.font_size)) or self.font_size <= 0:
            raise ValueError("font_size must be positive and finite")


@dataclass(frozen=True, slots=True)
class AddMarker:
    points: tuple[PointMM, PointMM]
    border_width: int
    border_color: Color = Color.YELLOW
    border_transparent: bool = True
    kind: Literal["marker"] = "marker"

    def __post_init__(self) -> None:
        if len(self.points) != 2 or not all(isinstance(p, PointMM) for p in self.points):
            raise ValueError("marker requires two PointMM values")
        if isinstance(self.border_width, bool) or not isinstance(self.border_width, int) or self.border_width < 1:
            raise ValueError("marker width must be a positive integer in points")


PlanOperation = AddRectangle | AddText | AddMarker


@dataclass(frozen=True, slots=True)
class AnnotationPlan:
    image_path: Path
    page: int
    pixel_width: int
    pixel_height: int
    page_width_mm: float
    page_height_mm: float
    regions: tuple[OcrRegion, ...]
    operations: tuple[PlanOperation, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "image_path", Path(self.image_path).expanduser().resolve())
        if isinstance(self.page, bool) or not isinstance(self.page, int) or self.page < 1:
            raise ValueError("page must be a positive one-based integer")

    def to_dict(self) -> dict[str, Any]:
        operations: list[dict[str, Any]] = []
        for operation in self.operations:
            if isinstance(operation, AddRectangle):
                operations.append({"kind": operation.kind, "rect_mm": asdict(operation.rect)})
            elif isinstance(operation, AddMarker):
                operations.append({"kind": "marker", "points_mm": [asdict(p) for p in operation.points],
                                   "border_width_pt": operation.border_width,
                                   "border_color": int(operation.border_color),
                                   "border_transparent": operation.border_transparent})
            else:
                operations.append(
                    {
                        "kind": operation.kind,
                        "text": operation.text,
                        "position_mm": asdict(operation.position),
                        "font_size_pt": operation.font_size,
                    }
                )
        return {
            "image_path": str(self.image_path),
            "page": self.page,
            "image_pixels": {"width": self.pixel_width, "height": self.pixel_height},
            "page_mm": {"width": self.page_width_mm, "height": self.page_height_mm},
            "regions": [
                {"text": region.text, "bbox": asdict(region.bbox), "confidence": region.confidence,
                 **({"polygon": [asdict(p) for p in region.polygon]} if region.polygon else {})}
                for region in self.regions
            ],
            "operations": operations,
        }


@dataclass(frozen=True, slots=True)
class ExecutionReport:
    status: Literal["DRY_RUN", "VERIFIED"]
    input_xdw: str
    output_xdw: str
    image_path: str
    page: int
    planned_operations: int
    executed_operations: int
    annotations_before: int | None
    annotations_after: int | None
    input_sha256_before: str
    input_sha256_after: str
    image_sha256: str
    output_sha256: str | None
    verified: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
