from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

from ._raw import constants as C
from .attributes import AttributeCondition
from .geometry import SizeMM


HeightBehavior = Literal["independent", "equal_width"]


@dataclass(frozen=True)
class AnnotationCapabilitySpec:
    annotation_type: int
    resizable: bool
    minimum_width_mm: float | None = None
    maximum_width_mm: float | None = None
    minimum_height_mm: float | None = None
    maximum_height_mm: float | None = None
    height_behavior: HeightBehavior = "independent"
    resize_conditions: tuple[AttributeCondition, ...] = ()


def _condition(name: str, value: int) -> tuple[AttributeCondition, ...]:
    return (AttributeCondition(name, value),)


ANNOTATION_CAPABILITIES: dict[int, AnnotationCapabilitySpec] = {
    C.XDW_AID_RECTANGLE: AnnotationCapabilitySpec(
        C.XDW_AID_RECTANGLE, True, 3, 2400, 3, 2400
    ),
    C.XDW_AID_ARC: AnnotationCapabilitySpec(
        C.XDW_AID_ARC, True, 3, 2400, 3, 2400
    ),
    C.XDW_AID_TEXT: AnnotationCapabilitySpec(
        C.XDW_AID_TEXT,
        True,
        5,
        2400,
        5,
        2400,
        resize_conditions=(
            AttributeCondition(C.XDW_ATN_WordWrap, 1),
            AttributeCondition(C.XDW_ATN_TextOrientation, 0),
        ),
    ),
    C.XDW_AID_BITMAP: AnnotationCapabilitySpec(
        C.XDW_AID_BITMAP, True, 5, 2400, 5, 2400
    ),
    C.XDW_AID_LINK: AnnotationCapabilitySpec(
        C.XDW_AID_LINK,
        True,
        5,
        2400,
        5,
        2400,
        resize_conditions=_condition(C.XDW_ATN_AutoResize, 0),
    ),
    C.XDW_AID_FUSEN: AnnotationCapabilitySpec(
        C.XDW_AID_FUSEN, True, 5, 500, 5, 500
    ),
    C.XDW_AID_STAMP: AnnotationCapabilitySpec(
        C.XDW_AID_STAMP,
        True,
        10,
        500,
        10,
        500,
        height_behavior="equal_width",
    ),
}


def annotation_capability(annotation_type: int) -> AnnotationCapabilitySpec:
    return ANNOTATION_CAPABILITIES.get(
        int(annotation_type),
        AnnotationCapabilitySpec(int(annotation_type), False),
    )


def validate_annotation_size(
    spec: AnnotationCapabilitySpec,
    size: SizeMM,
    *,
    context: Mapping[str, object] | None = None,
) -> SizeMM:
    if not spec.resizable:
        raise ValueError(
            f"annotation type {spec.annotation_type} cannot be resized by XDWAPI"
        )
    normalized = (
        SizeMM(size.width, size.width)
        if spec.height_behavior == "equal_width"
        else size
    )
    if spec.minimum_width_mm is not None and normalized.width < spec.minimum_width_mm:
        raise ValueError(f"width must be >= {spec.minimum_width_mm} mm")
    if spec.maximum_width_mm is not None and normalized.width > spec.maximum_width_mm:
        raise ValueError(f"width must be <= {spec.maximum_width_mm} mm")
    if spec.minimum_height_mm is not None and normalized.height < spec.minimum_height_mm:
        raise ValueError(f"height must be >= {spec.minimum_height_mm} mm")
    if spec.maximum_height_mm is not None and normalized.height > spec.maximum_height_mm:
        raise ValueError(f"height must be <= {spec.maximum_height_mm} mm")
    if context is not None:
        for condition in spec.resize_conditions:
            if context.get(condition.attribute_name) != condition.equals:
                raise ValueError(
                    "resize requires "
                    f"{condition.attribute_name} == {condition.equals}"
                )
    return normalized

