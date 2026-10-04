from __future__ import annotations

import ctypes
from pathlib import Path
from typing import Iterator, Sequence

from ._raw import constants as C
from ._raw import types as T
from .attributes import (
    CustomAttribute,
    CustomAttributeKind,
    delete_custom_attribute,
    delete_user_attribute,
    get_custom_attribute,
    get_standard_attribute,
    get_standard_attribute_raw,
    get_user_attribute,
    list_custom_attributes,
    set_custom_attribute,
    set_standard_attribute,
    set_standard_attribute_raw,
    set_user_attribute,
    standard_attribute_spec,
    validate_standard_raw_value,
    validate_standard_value,
)
from .capabilities import annotation_capability, validate_annotation_size
from .encoding import MultibyteEncodingPolicy, wchar_buffer
from .enums import (
    AnnotationType,
    ArrowheadStyle,
    ArrowheadType,
    BorderType,
    Color,
    LinkType,
    OpenMode,
)
from .errors import (
    AnnotationRefreshError,
    ClosedHandleError,
    ReadOnlyDocumentError,
    check_result,
)
from .geometry import PointMM, RectMM, SizeMM, mm_to_xdw, position_to_xdw, xdw_to_mm


class Document:
    def __init__(
        self,
        raw,
        handle,
        path: Path,
        mode: OpenMode,
        multibyte_encoding: MultibyteEncodingPolicy | None = None,
    ):
        self.raw = raw
        self.handle = handle
        self.path = path
        self.mode = OpenMode(mode)
        self.multibyte_encoding = (
            multibyte_encoding or MultibyteEncodingPolicy.create()
        )
        self._closed = False

    def __enter__(self) -> "Document":
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        try:
            self.close()
        except Exception as close_error:
            if exc is None:
                raise
            # Cleanup diagnostics must never replace the original exception.
            try:
                add_note = getattr(exc, "add_note", None)
                if callable(add_note):
                    add_note(f"文書クローズ時にもエラーが発生しました: {close_error}")
            except Exception:
                pass
        return False

    @property
    def closed(self) -> bool:
        return self._closed

    def _ensure_open(self) -> None:
        if self._closed:
            raise ClosedHandleError("文書ハンドルは既に閉じています")

    def _ensure_update(self) -> None:
        self._ensure_open()
        if self.mode != OpenMode.UPDATE:
            raise ReadOnlyDocumentError("文書は読み取り専用で開かれています")

    @property
    def page_count(self) -> int:
        self._ensure_open()
        info = T.XDW_DOCUMENT_INFO()
        info.nSize = ctypes.sizeof(info)
        result = self.raw.XDW_GetDocumentInformation(self.handle, ctypes.byref(info))
        check_result(result, "XDW_GetDocumentInformation")
        return info.nPages

    def page(self, number: int) -> "Page":
        self._ensure_open()
        if number < 1:
            raise IndexError("ページ番号は1始まりです")
        count = self.page_count
        if number > count:
            raise IndexError(f"ページ番号が範囲外です: {number} (ページ数={count})")
        return Page(self, number)

    def save(self) -> None:
        self._ensure_update()
        result = self.raw.XDW_SaveDocument(self.handle, None)
        check_result(result, "XDW_SaveDocument")

    def close(self) -> None:
        if self._closed:
            return
        result = self.raw.XDW_CloseDocumentHandle(self.handle, None)
        self._closed = True
        self.handle = T.XDW_DOCUMENT_HANDLE()
        check_result(result, "XDW_CloseDocumentHandle")


class Page:
    def __init__(self, document: Document, number: int):
        self.document = document
        self.number = number

    @property
    def raw(self):
        return self.document.raw

    def _ensure_open(self):
        self.document._ensure_open()

    def _ensure_update(self):
        self.document._ensure_update()

    def _page_info(self) -> T.XDW_PAGE_INFO:
        self._ensure_open()
        info = T.XDW_PAGE_INFO()
        info.nSize = ctypes.sizeof(info)
        result = self.raw.XDW_GetPageInformation(
            self.document.handle, self.number, ctypes.byref(info)
        )
        check_result(result, "XDW_GetPageInformation")
        return info

    def _get_annotation_info(self, parent_handle, index: int) -> T.XDW_ANNOTATION_INFO:
        info = T.XDW_ANNOTATION_INFO()
        info.nSize = ctypes.sizeof(info)
        result = self.raw.XDW_GetAnnotationInformation(
            self.document.handle,
            self.number,
            parent_handle,
            index,
            ctypes.byref(info),
            None,
        )
        check_result(result, "XDW_GetAnnotationInformation")
        return info

    def _children(self, parent_handle, count: int) -> Iterator["Annotation"]:
        for index in range(1, count + 1):
            info = self._get_annotation_info(parent_handle, index)
            yield Annotation(self, info)

    def annotations(self, recursive: bool = True) -> Iterator["Annotation"]:
        page_info = self._page_info()
        for annotation in self._children(None, page_info.nAnnotations):
            yield annotation
            if recursive:
                yield from annotation.descendants()

    def _find_annotation(self, handle_value: int | None) -> "Annotation | None":
        for annotation in self.annotations(recursive=True):
            if annotation.handle_value == handle_value:
                return annotation
        return None

    def _refresh_added_annotation(
        self,
        new_handle,
        *,
        parent: "Annotation | None" = None,
    ) -> "Annotation":
        expected_handle = new_handle.value
        if parent is None:
            parent_handle = None
            count = self._page_info().nAnnotations
        else:
            parent_handle = parent.handle
            count = parent._info.nChildAnnotations + 1
        for index in range(1, count + 1):
            info = self._get_annotation_info(parent_handle, index)
            if info.handle == expected_handle:
                if parent is not None:
                    parent._info.nChildAnnotations = count
                return Annotation(self, info)
        location = "page" if parent is None else f"parent {parent.handle_value}"
        raise AnnotationRefreshError(
            f"added annotation handle {expected_handle} was not found under {location}"
        )

    def _initial_common(self, data, annotation_type: AnnotationType) -> None:
        data.common.nSize = ctypes.sizeof(data)
        data.common.nAnnotationType = int(annotation_type)
        data.common.nReserved1 = 0
        data.common.nReserved2 = 0

    def _add(
        self,
        annotation_type: AnnotationType,
        position: PointMM,
        initial_data=None,
        *,
        parent: "Annotation | None" = None,
        known_size: SizeMM | None = None,
    ) -> "Annotation":
        self._ensure_update()
        if known_size is not None:
            validate_annotation_size(
                annotation_capability(int(annotation_type)), known_size
            )
        initial_pointer = None
        if initial_data is not None:
            initial_pointer = ctypes.cast(
                ctypes.byref(initial_data), ctypes.POINTER(T.XDW_AA_INITIAL_DATA)
            )
        new_handle = T.XDW_ANNOTATION_HANDLE()
        x, y = position_to_xdw(position.x), position_to_xdw(position.y)
        if parent is None:
            result = self.raw.XDW_AddAnnotation(
                self.document.handle,
                int(annotation_type),
                self.number,
                x,
                y,
                initial_pointer,
                ctypes.byref(new_handle),
                None,
            )
        else:
            parent._ensure_valid()
            result = self.raw.XDW_AddAnnotationOnParentAnnotation(
                self.document.handle,
                parent.handle,
                int(annotation_type),
                x,
                y,
                initial_pointer,
                ctypes.byref(new_handle),
                None,
            )
        check_result(result, "XDW_AddAnnotation")
        return self._refresh_added_annotation(new_handle, parent=parent)

    def add_rectangle(
        self,
        rect: RectMM,
        *,
        border_color: Color | int | None = None,
        border_width: int | None = None,
        border_visible: bool | None = None,
        fill_color: Color | int | None = None,
        fill_visible: bool | None = None,
        fill_transparent: bool | None = None,
    ) -> "Annotation":
        data = T.XDW_AA_RECT_INITIAL_DATA()
        self._initial_common(data, AnnotationType.RECTANGLE)
        data.nWidth = mm_to_xdw(rect.width)
        data.nHeight = mm_to_xdw(rect.height)
        annotation = self._add(
            AnnotationType.RECTANGLE,
            PointMM(rect.x, rect.y),
            data,
            known_size=SizeMM(rect.width, rect.height),
        )
        annotation._apply_style(
            border_color=border_color,
            border_width=border_width,
            border_visible=border_visible,
            fill_color=fill_color,
            fill_visible=fill_visible,
            fill_transparent=fill_transparent,
        )
        return annotation

    def add_text(
        self,
        position: PointMM,
        text: str,
        *,
        font_name: str | None = None,
        font_size: float | None = None,
        font_style: int | None = None,
        fore_color: Color | int | None = None,
        back_color: Color | int | None = None,
        parent: "Annotation | None" = None,
    ) -> "Annotation":
        validate_standard_value(
            standard_attribute_spec(C.XDW_AID_TEXT, C.XDW_ATN_Text), text,
            encoding_policy=self.document.multibyte_encoding,
        )
        if font_name is not None:
            self.document.multibyte_encoding.encode(font_name)
        annotation = self._add(AnnotationType.TEXT, position, parent=parent)
        annotation.set_standard_attribute(C.XDW_ATN_Text, text)
        for name, value in (
            (C.XDW_ATN_FontName, font_name),
            (C.XDW_ATN_FontSize, font_size),
            (C.XDW_ATN_FontStyle, font_style),
            (C.XDW_ATN_ForeColor, fore_color),
            (C.XDW_ATN_BackColor, back_color),
        ):
            if value is not None:
                annotation.set_standard_attribute(name, value)
        return annotation

    def add_sticky(
        self,
        position: PointMM,
        size: SizeMM,
        *,
        fill_color: Color | int | None = None,
        auto_resize: bool | None = None,
        text: str | None = None,
        text_position: PointMM = PointMM(2, 2),
    ) -> "Annotation":
        if text is not None:
            validate_standard_value(
                standard_attribute_spec(C.XDW_AID_TEXT, C.XDW_ATN_Text), text,
                encoding_policy=self.document.multibyte_encoding,
            )
        data = T.XDW_AA_FUSEN_INITIAL_DATA()
        self._initial_common(data, AnnotationType.STICKY)
        data.nWidth = mm_to_xdw(size.width)
        data.nHeight = mm_to_xdw(size.height)
        annotation = self._add(
            AnnotationType.STICKY, position, data, known_size=size
        )
        if fill_color is not None:
            annotation.set_standard_attribute(C.XDW_ATN_FillColor, fill_color)
        if auto_resize is not None:
            annotation.set_standard_attribute(C.XDW_ATN_AutoResize, auto_resize)
        if text is not None:
            self.add_text(text_position, text, parent=annotation)
        return annotation

    def add_line(
        self,
        start: PointMM,
        end: PointMM,
        *,
        border_color: Color | int | None = None,
        border_width: int | None = None,
        border_type: BorderType | int | None = None,
        border_transparent: bool | None = None,
        arrowhead_type: ArrowheadType | int | None = None,
        arrowhead_style: ArrowheadStyle | int | None = None,
    ) -> "Annotation":
        data = T.XDW_AA_STRAIGHTLINE_INITIAL_DATA()
        self._initial_common(data, AnnotationType.STRAIGHT_LINE)
        data.nHorVec = position_to_xdw(end.x - start.x)
        data.nVerVec = position_to_xdw(end.y - start.y)
        annotation = self._add(AnnotationType.STRAIGHT_LINE, start, data)
        annotation._apply_style(
            border_color=border_color,
            border_width=border_width,
            border_type=border_type,
            border_transparent=border_transparent,
            arrowhead_style=arrowhead_style,
        )
        if arrowhead_type is not None:
            annotation.set_standard_attribute(C.XDW_ATN_ArrowheadType, int(arrowhead_type))
        return annotation

    def add_ellipse(
        self,
        rect: RectMM,
        *,
        border_color: Color | int | None = None,
        border_width: int | None = None,
        border_visible: bool | None = None,
        fill_color: Color | int | None = None,
        fill_visible: bool | None = None,
        fill_transparent: bool | None = None,
    ) -> "Annotation":
        data = T.XDW_AA_ARC_INITIAL_DATA()
        self._initial_common(data, AnnotationType.ELLIPSE)
        data.nWidth = mm_to_xdw(rect.width)
        data.nHeight = mm_to_xdw(rect.height)
        annotation = self._add(
            AnnotationType.ELLIPSE,
            PointMM(rect.x, rect.y),
            data,
            known_size=SizeMM(rect.width, rect.height),
        )
        annotation._apply_style(
            border_color=border_color,
            border_width=border_width,
            border_visible=border_visible,
            fill_color=fill_color,
            fill_visible=fill_visible,
            fill_transparent=fill_transparent,
        )
        return annotation

    @staticmethod
    def _initial_point_array(points: Sequence[PointMM]):
        if not points:
            raise ValueError("points requires at least one PointMM")
        if not all(isinstance(point, PointMM) for point in points):
            raise TypeError("points requires a sequence of PointMM")
        raw_points: list[tuple[int, int]] = []
        first: tuple[int, int] | None = None
        for point in points:
            absolute = (mm_to_xdw(point.x), mm_to_xdw(point.y))
            encoded = absolute if first is None else (
                absolute[0] - first[0],
                absolute[1] - first[1],
            )
            if not all(-240000 <= coordinate <= 240000 for coordinate in encoded):
                raise ValueError("point coordinates must be between -2400 and 2400 mm")
            raw_points.append(encoded)
            if first is None:
                first = absolute
        storage = (T.XDW_POINT * len(raw_points))()
        for index, (x, y) in enumerate(raw_points):
            storage[index].x = x
            storage[index].y = y
        return storage

    def add_polygon(
        self,
        points: Sequence[PointMM],
        *,
        close: bool = True,
        border_color: Color | int | None = None,
        border_width: int | None = None,
        border_visible: bool | None = None,
        fill_color: Color | int | None = None,
        fill_visible: bool | None = None,
        fill_transparent: bool | None = None,
        arrowhead_type: ArrowheadType | int | None = None,
        arrowhead_style: ArrowheadStyle | int | None = None,
    ) -> "Annotation":
        storage = self._initial_point_array(points)
        data = T.XDW_AA_POLYGON_INITIAL_DATA()
        self._initial_common(data, AnnotationType.POLYGON)
        data.nCounts = len(storage)
        data.pPoints = ctypes.cast(storage, ctypes.POINTER(T.XDW_POINT))
        annotation = self._add(AnnotationType.POLYGON, PointMM(0, 0), data)
        annotation.set_standard_attribute(C.XDW_ATN_Close, close)
        annotation._apply_style(
            border_color=border_color,
            border_width=border_width,
            border_visible=border_visible,
            fill_color=fill_color,
            fill_visible=fill_visible,
            fill_transparent=fill_transparent,
            arrowhead_type=arrowhead_type,
            arrowhead_style=arrowhead_style,
        )
        return annotation

    def add_marker(
        self,
        points: Sequence[PointMM],
        *,
        border_color: Color | int | None = None,
        border_width: int | None = None,
        border_transparent: bool | None = None,
    ) -> "Annotation":
        storage = self._initial_point_array(points)
        data = T.XDW_AA_MARKER_INITIAL_DATA()
        self._initial_common(data, AnnotationType.MARKER)
        data.nCounts = len(storage)
        data.pPoints = ctypes.cast(storage, ctypes.POINTER(T.XDW_POINT))
        annotation = self._add(AnnotationType.MARKER, PointMM(0, 0), data)
        annotation._apply_style(
            border_color=border_color,
            border_width=border_width,
            border_transparent=border_transparent,
        )
        return annotation

    def add_link(
        self,
        position: PointMM,
        caption: str,
        *,
        link_type: LinkType | int,
        target: str | None = None,
        auto_resize: bool = True,
        size: SizeMM | None = None,
        fore_color: Color | int | None = None,
        font_size: float | None = None,
    ) -> "Annotation":
        normalized_type = LinkType(int(link_type))
        if normalized_type is LinkType.THIS_DOCUMENT:
            if target is not None:
                raise ValueError("THIS_DOCUMENT link does not accept target")
        elif not isinstance(target, str) or not target:
            raise ValueError(f"{normalized_type.name} link requires a non-empty target")
        if size is not None and auto_resize:
            raise ValueError("size requires auto_resize=False")
        validate_standard_value(
            standard_attribute_spec(C.XDW_AID_LINK, C.XDW_ATN_Caption), caption,
            encoding_policy=self.document.multibyte_encoding,
        )
        if target is not None:
            # Validate the target string before creating a native annotation.
            self.document.multibyte_encoding.encoded_length(target, unicode_allowed=True)
        annotation = self._add(AnnotationType.LINK, position)
        annotation.set_standard_attribute(C.XDW_ATN_Caption, caption)
        annotation.set_standard_attribute(C.XDW_ATN_LinkType, int(normalized_type))
        annotation.set_standard_attribute(C.XDW_ATN_AutoResize, auto_resize)
        target_attributes = {
            LinkType.XDW: C.XDW_ATN_XdwPath,
            LinkType.URL: C.XDW_ATN_Url,
            LinkType.OTHER_FILE: C.XDW_ATN_OtherFilePath,
            LinkType.MAIL_ADDRESS: C.XDW_ATN_MailAddress,
        }
        target_attribute = target_attributes.get(normalized_type)
        if target_attribute is not None:
            annotation.set_standard_attribute(target_attribute, target)
        if fore_color is not None:
            annotation.set_standard_attribute(C.XDW_ATN_ForeColor, fore_color)
        if font_size is not None:
            annotation.set_standard_attribute(C.XDW_ATN_FontSize, font_size)
        if size is not None:
            annotation.set_size(size)
        return annotation

    def add_from_ann(
        self,
        ann_path: str | Path,
        position: PointMM,
        *,
        index: int = 1,
        parent: "Annotation | None" = None,
    ) -> "Annotation":
        self._ensure_update()
        if index < 1:
            raise ValueError("ANN内のアノテーション番号は1始まりです")
        path = Path(ann_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        path_buffer = wchar_buffer(str(path))
        new_handle = T.XDW_ANNOTATION_HANDLE()
        parent_handle = parent.handle if parent is not None else None
        result = self.raw.XDW_AddAnnotationFromAnnFileW(
            self.document.handle,
            path_buffer,
            index,
            self.number,
            parent_handle,
            position_to_xdw(position.x),
            position_to_xdw(position.y),
            ctypes.byref(new_handle),
            None,
        )
        check_result(result, "XDW_AddAnnotationFromAnnFileW")
        return self._refresh_added_annotation(new_handle, parent=parent)


class Annotation:
    def __init__(self, page: Page, info: T.XDW_ANNOTATION_INFO):
        self.page = page
        self._info = info
        self._removed = False

    @property
    def document(self) -> Document:
        return self.page.document

    @property
    def raw(self):
        return self.page.raw

    @property
    def handle(self):
        return T.XDW_ANNOTATION_HANDLE(self.handle_value)

    @property
    def handle_value(self) -> int | None:
        return self._info.handle

    @property
    def annotation_type(self) -> AnnotationType | int:
        try:
            return AnnotationType(self._info.nAnnotationType)
        except ValueError:
            return self._info.nAnnotationType

    @property
    def position(self) -> PointMM:
        return PointMM(xdw_to_mm(self._info.nHorPos), xdw_to_mm(self._info.nVerPos))

    @property
    def size(self) -> SizeMM | None:
        if self._info.nWidth <= 0 or self._info.nHeight <= 0:
            return None
        return SizeMM(xdw_to_mm(self._info.nWidth), xdw_to_mm(self._info.nHeight))

    def _ensure_valid(self) -> None:
        self.document._ensure_open()
        if self._removed:
            raise ClosedHandleError("アノテーションは既に削除されています")

    def descendants(self) -> Iterator["Annotation"]:
        self._ensure_valid()
        for child in self.page._children(self.handle, self._info.nChildAnnotations):
            yield child
            yield from child.descendants()

    def set_standard_attribute(self, name: str, value) -> None:
        self._ensure_valid()
        self.document._ensure_update()
        spec = standard_attribute_spec(int(self.annotation_type), name)
        context = {
            condition.attribute_name: self.get_standard_attribute_raw(
                condition.attribute_name
            )
            for condition in spec.conditions
        }
        validate_standard_value(
            spec,
            value,
            context=context,
            encoding_policy=self.document.multibyte_encoding,
        )
        set_standard_attribute(
            self.raw,
            self.document.handle,
            self.handle,
            spec,
            value,
            encoding_policy=self.document.multibyte_encoding,
        )

    def get_standard_attribute(self, name: str):
        self._ensure_valid()
        spec = standard_attribute_spec(int(self.annotation_type), name)
        return get_standard_attribute(
            self.raw,
            self.handle,
            spec,
            encoding_policy=self.document.multibyte_encoding,
        )

    def set_standard_attribute_raw(self, name: str, value) -> None:
        self._ensure_valid()
        self.document._ensure_update()
        spec = standard_attribute_spec(int(self.annotation_type), name)
        context = {
            condition.attribute_name: self.get_standard_attribute_raw(
                condition.attribute_name
            )
            for condition in spec.conditions
        }
        validate_standard_raw_value(
            spec,
            value,
            context=context,
            encoding_policy=self.document.multibyte_encoding,
        )
        set_standard_attribute_raw(
            self.raw,
            self.document.handle,
            self.handle,
            spec,
            value,
            encoding_policy=self.document.multibyte_encoding,
        )

    def get_standard_attribute_raw(self, name: str):
        self._ensure_valid()
        spec = standard_attribute_spec(int(self.annotation_type), name)
        return get_standard_attribute_raw(
            self.raw,
            self.handle,
            spec,
            encoding_policy=self.document.multibyte_encoding,
        )

    def set_custom_attribute(self, name: str, kind: CustomAttributeKind, value) -> int:
        self._ensure_valid()
        self.document._ensure_update()
        return set_custom_attribute(
            self.raw, self.document.handle, self.handle, name, kind, value
        )

    def get_custom_attribute(self, name: str) -> CustomAttribute:
        self._ensure_valid()
        return get_custom_attribute(self.raw, self.handle, name)

    def custom_attributes(self) -> tuple[CustomAttribute, ...]:
        self._ensure_valid()
        return list_custom_attributes(self.raw, self.handle)

    def delete_custom_attribute(self, name: str) -> int:
        self._ensure_valid()
        self.document._ensure_update()
        return delete_custom_attribute(
            self.raw, self.document.handle, self.handle, name
        )

    def set_user_attribute(self, name: str, value: bytes) -> None:
        self._ensure_valid()
        self.document._ensure_update()
        set_user_attribute(
            self.raw,
            self.document.handle,
            self.handle,
            name,
            value,
            encoding_policy=self.document.multibyte_encoding,
        )

    def get_user_attribute(self, name: str) -> bytes:
        self._ensure_valid()
        return get_user_attribute(
            self.raw,
            self.handle,
            name,
            encoding_policy=self.document.multibyte_encoding,
        )

    def delete_user_attribute(self, name: str) -> None:
        self._ensure_valid()
        self.document._ensure_update()
        delete_user_attribute(
            self.raw,
            self.document.handle,
            self.handle,
            name,
            encoding_policy=self.document.multibyte_encoding,
        )

    def _apply_style(
        self,
        *,
        border_color=None,
        border_width=None,
        border_type=None,
        border_transparent=None,
        border_visible=None,
        fill_color=None,
        fill_visible=None,
        fill_transparent=None,
        arrowhead_type=None,
        arrowhead_style=None,
    ) -> None:
        for name, value in (
            (C.XDW_ATN_BorderColor, border_color),
            (C.XDW_ATN_BorderWidth, border_width),
            (C.XDW_ATN_BorderType, border_type),
            (C.XDW_ATN_BorderTransparent, border_transparent),
            (C.XDW_ATN_BorderStyle, border_visible),
            (C.XDW_ATN_FillColor, fill_color),
            (C.XDW_ATN_FillStyle, fill_visible),
            (C.XDW_ATN_FillTransparent, fill_transparent),
            (C.XDW_ATN_ArrowheadType, arrowhead_type),
            (C.XDW_ATN_ArrowheadStyle, arrowhead_style),
        ):
            if value is not None:
                self.set_standard_attribute(name, value)

    def set_position(self, position: PointMM) -> None:
        self._ensure_valid()
        self.document._ensure_update()
        x, y = position_to_xdw(position.x), position_to_xdw(position.y)
        result = self.raw.XDW_SetAnnotationPosition(
            self.document.handle, self.handle, x, y, None
        )
        check_result(result, "XDW_SetAnnotationPosition")
        self._info.nHorPos = x
        self._info.nVerPos = y

    def set_size(self, size: SizeMM) -> None:
        self._ensure_valid()
        self.document._ensure_update()
        capability = annotation_capability(int(self.annotation_type))
        context = {
            condition.attribute_name: self.get_standard_attribute_raw(
                condition.attribute_name
            )
            for condition in capability.resize_conditions
        }
        normalized = validate_annotation_size(
            capability,
            size,
            context=context,
        )
        width, height = mm_to_xdw(normalized.width), mm_to_xdw(normalized.height)
        result = self.raw.XDW_SetAnnotationSize(
            self.document.handle, self.handle, width, height, None
        )
        check_result(result, "XDW_SetAnnotationSize")
        self._info.nWidth = width
        self._info.nHeight = height

    def remove(self) -> None:
        self._ensure_valid()
        self.document._ensure_update()
        result = self.raw.XDW_RemoveAnnotation(
            self.document.handle, self.handle, None
        )
        check_result(result, "XDW_RemoveAnnotation")
        self._removed = True
