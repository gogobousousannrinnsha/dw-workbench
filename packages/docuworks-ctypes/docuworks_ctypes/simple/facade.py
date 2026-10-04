from __future__ import annotations

from enum import IntEnum
from pathlib import Path
from typing import Sequence, TypeVar

from ..api import XdwApi
from ..document import Annotation, Document, Page
from ..enums import (
    AnnotationType,
    ArrowheadStyle,
    ArrowheadType,
    BorderType,
    Color,
    LinkType,
    OpenMode,
)
from ..geometry import PointMM, RectMM, SizeMM


_EnumT = TypeVar("_EnumT", bound=IntEnum)


def _require_enum(name: str, value: object, enum_type: type[_EnumT]) -> _EnumT:
    if not isinstance(value, enum_type):
        raise TypeError(f"{name} must be {enum_type.__name__}")
    return value


def _optional_enum(
    name: str, value: object | None, enum_type: type[_EnumT]
) -> _EnumT | None:
    if value is None:
        return None
    return _require_enum(name, value, enum_type)


class SimpleAnnotation:
    """Natural-unit facade over one live Core Annotation."""

    def __init__(self, core: Annotation):
        self._core = core

    def _ensure_valid(self) -> None:
        self._core._ensure_valid()

    @property
    def type(self) -> AnnotationType | int:
        self._ensure_valid()
        return self._core.annotation_type

    @property
    def position(self) -> PointMM:
        self._ensure_valid()
        return self._core.position

    @property
    def size(self) -> SizeMM | None:
        self._ensure_valid()
        return self._core.size

    @property
    def core(self) -> Annotation:
        self._ensure_valid()
        return self._core

    def move_to(self, *, x: float, y: float) -> None:
        self._ensure_valid()
        self._core.set_position(PointMM(x, y))

    def resize(self, *, width: float, height: float) -> None:
        self._ensure_valid()
        self._core.set_size(SizeMM(width, height))

    def delete(self) -> None:
        self._ensure_valid()
        self._core.remove()


class SimpleDocument:
    def __init__(self, core: Document):
        self.core = core

    def __enter__(self) -> "SimpleDocument":
        self.core.__enter__()
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return self.core.__exit__(exc_type, exc, traceback)

    def page(self, number: int = 1) -> "SimplePage":
        return SimplePage(self.core.page(number))

    def save(self) -> None:
        self.core.save()

    def close(self) -> None:
        self.core.close()


class SimplePage:
    def __init__(self, core: Page):
        self.core = core

    @staticmethod
    def _wrap(annotation: Annotation) -> SimpleAnnotation:
        return SimpleAnnotation(annotation)

    def annotations(self, *, recursive: bool = False) -> tuple[SimpleAnnotation, ...]:
        return tuple(
            self._wrap(annotation)
            for annotation in self.core.annotations(recursive=recursive)
        )

    def text(
        self,
        text: str,
        *,
        x: float,
        y: float,
        font_size: float = 12.0,
        font_name: str | None = None,
        fore_color: Color | None = None,
        back_color: Color | None = None,
    ) -> SimpleAnnotation:
        fore_color = _optional_enum("fore_color", fore_color, Color)
        back_color = _optional_enum("back_color", back_color, Color)
        return self._wrap(
            self.core.add_text(
                PointMM(x, y),
                text,
                font_name=font_name,
                font_size=font_size,
                fore_color=fore_color,
                back_color=back_color,
            )
        )

    def rectangle(
        self,
        *,
        x: float,
        y: float,
        width: float,
        height: float,
        border_color: Color | None = None,
        border_width: int | None = None,
        border_visible: bool | None = None,
        fill_color: Color | None = None,
        fill_visible: bool | None = None,
        fill_transparent: bool | None = None,
    ) -> SimpleAnnotation:
        border_color = _optional_enum("border_color", border_color, Color)
        fill_color = _optional_enum("fill_color", fill_color, Color)
        return self._wrap(
            self.core.add_rectangle(
                RectMM(x, y, width, height),
                border_color=border_color,
                border_width=border_width,
                border_visible=border_visible,
                fill_color=fill_color,
                fill_visible=fill_visible,
                fill_transparent=fill_transparent,
            )
        )

    def sticky(
        self,
        *,
        x: float,
        y: float,
        width: float,
        height: float,
        fill_color: Color | None = None,
        auto_resize: bool | None = None,
        text: str | None = None,
    ) -> SimpleAnnotation:
        fill_color = _optional_enum("fill_color", fill_color, Color)
        return self._wrap(
            self.core.add_sticky(
                PointMM(x, y),
                SizeMM(width, height),
                fill_color=fill_color,
                auto_resize=auto_resize,
                text=text,
            )
        )

    def ellipse(
        self,
        *,
        x: float,
        y: float,
        width: float,
        height: float,
        border_color: Color | None = None,
        border_width: int | None = None,
        border_visible: bool | None = None,
        fill_color: Color | None = None,
        fill_visible: bool | None = None,
        fill_transparent: bool | None = None,
    ) -> SimpleAnnotation:
        border_color = _optional_enum("border_color", border_color, Color)
        fill_color = _optional_enum("fill_color", fill_color, Color)
        return self._wrap(
            self.core.add_ellipse(
                RectMM(x, y, width, height),
                border_color=border_color,
                border_width=border_width,
                border_visible=border_visible,
                fill_color=fill_color,
                fill_visible=fill_visible,
                fill_transparent=fill_transparent,
            )
        )

    def line(
        self,
        *,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        border_color: Color | None = None,
        border_width: int | None = None,
        border_type: BorderType | None = None,
        border_transparent: bool | None = None,
        arrowhead_type: ArrowheadType | None = None,
        arrowhead_style: ArrowheadStyle | None = None,
    ) -> SimpleAnnotation:
        border_color = _optional_enum("border_color", border_color, Color)
        border_type = _optional_enum("border_type", border_type, BorderType)
        arrowhead_type = _optional_enum(
            "arrowhead_type", arrowhead_type, ArrowheadType
        )
        arrowhead_style = _optional_enum(
            "arrowhead_style", arrowhead_style, ArrowheadStyle
        )
        return self._wrap(
            self.core.add_line(
                PointMM(x1, y1),
                PointMM(x2, y2),
                border_color=border_color,
                border_width=border_width,
                border_type=border_type,
                border_transparent=border_transparent,
                arrowhead_type=arrowhead_type,
                arrowhead_style=arrowhead_style,
            )
        )

    def polygon(
        self,
        points: Sequence[PointMM],
        *,
        close: bool = True,
        border_color: Color | None = None,
        border_width: int | None = None,
        border_visible: bool | None = None,
        fill_color: Color | None = None,
        fill_visible: bool | None = None,
        fill_transparent: bool | None = None,
        arrowhead_type: ArrowheadType | None = None,
        arrowhead_style: ArrowheadStyle | None = None,
    ) -> SimpleAnnotation:
        border_color = _optional_enum("border_color", border_color, Color)
        fill_color = _optional_enum("fill_color", fill_color, Color)
        arrowhead_type = _optional_enum(
            "arrowhead_type", arrowhead_type, ArrowheadType
        )
        arrowhead_style = _optional_enum(
            "arrowhead_style", arrowhead_style, ArrowheadStyle
        )
        return self._wrap(
            self.core.add_polygon(
                points,
                close=close,
                border_color=border_color,
                border_width=border_width,
                border_visible=border_visible,
                fill_color=fill_color,
                fill_visible=fill_visible,
                fill_transparent=fill_transparent,
                arrowhead_type=arrowhead_type,
                arrowhead_style=arrowhead_style,
            )
        )

    def marker(
        self,
        points: Sequence[PointMM],
        *,
        border_color: Color | None = None,
        border_width: int | None = None,
        border_transparent: bool | None = None,
    ) -> SimpleAnnotation:
        border_color = _optional_enum("border_color", border_color, Color)
        return self._wrap(
            self.core.add_marker(
                points,
                border_color=border_color,
                border_width=border_width,
                border_transparent=border_transparent,
            )
        )

    def link(
        self,
        caption: str,
        *,
        x: float,
        y: float,
        link_type: LinkType,
        target: str | None = None,
        auto_resize: bool = True,
        width: float | None = None,
        height: float | None = None,
        fore_color: Color | None = None,
        font_size: float | None = None,
    ) -> SimpleAnnotation:
        link_type = _require_enum("link_type", link_type, LinkType)
        fore_color = _optional_enum("fore_color", fore_color, Color)
        if (width is None) != (height is None):
            raise ValueError("width and height must be specified together")
        size = None if width is None else SizeMM(width, height)
        return self._wrap(
            self.core.add_link(
                PointMM(x, y),
                caption,
                link_type=link_type,
                target=target,
                auto_resize=auto_resize,
                size=size,
                fore_color=fore_color,
                font_size=font_size,
            )
        )


def open_xdw(
    path: str | Path,
    *,
    writable: bool = False,
    dll_path: str | Path | None = None,
    codepage: int | None = None,
) -> SimpleDocument:
    api = XdwApi.load(
        dll_path=dll_path,
        multibyte_codepage=codepage,
        verification_document=path,
    )
    mode = OpenMode.UPDATE if writable else OpenMode.READONLY
    return SimpleDocument(api.open_document(path, mode=mode))
