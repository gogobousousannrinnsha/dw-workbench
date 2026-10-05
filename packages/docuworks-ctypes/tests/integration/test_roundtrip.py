from __future__ import annotations

import ctypes
from pathlib import Path

import pytest

from docuworks_ctypes import (
    AnnotationType,
    ArrowheadStyle,
    ArrowheadType,
    BorderType,
    Color,
    CustomAttributeKind,
    LinkType,
    OpenMode,
    PointMM,
    RawPoint,
    RectMM,
    SizeMM,
    STANDARD_ATTRIBUTE_REGISTRY,
)
from docuworks_ctypes.simple import SimpleAnnotation, open_xdw
from docuworks_ctypes._raw import constants as C
from docuworks_ctypes._raw import types as T
from docuworks_ctypes.encoding import wchar_buffer
from docuworks_ctypes.errors import ClosedHandleError, ReadOnlyDocumentError, check_result


pytestmark = pytest.mark.integration


def _handle_value(handle):
    return getattr(handle, "value", handle)


def _latest(page, annotation_type):
    matches = [a for a in page.annotations() if a.annotation_type == annotation_type]
    if not matches:
        pytest.skip(f"fixture has no annotation of type {annotation_type}")
    return matches[-1]


def _annotations_in_document(document, annotation_type):
    return [
        (page_number, annotation)
        for page_number in range(1, document.page_count + 1)
        for annotation in document.page(page_number).annotations()
        if annotation.annotation_type == annotation_type
    ]


def _first_in_document(document, annotation_type):
    matches = _annotations_in_document(document, annotation_type)
    if not matches:
        pytest.fail(f"fixture has no annotation of type {annotation_type}")
    return matches[0]


def _text_type(annotation, name: str) -> int:
    result_type = ctypes.c_int32(C.XDW_TEXT_UNKNOWN)
    required = annotation.raw.XDW_GetAnnotationAttributeW(
        annotation.handle,
        name.encode("ascii"),
        None,
        0,
        ctypes.byref(result_type),
        annotation.document.multibyte_encoding.codepage,
        None,
    )
    check_result(required, f"XDW_GetAnnotationAttributeW({name}, text type)")
    return result_type.value


def _document_version(document) -> int:
    info = T.XDW_DOCUMENT_INFO()
    info.nSize = ctypes.sizeof(info)
    result = document.raw.XDW_GetDocumentInformation(
        document.handle, ctypes.byref(info)
    )
    check_result(result, "XDW_GetDocumentInformation(document version)")
    return int(info.nVersion)


def _rectangle_values(annotation):
    names = (
        C.XDW_ATN_BorderColor,
        C.XDW_ATN_BorderWidth,
        C.XDW_ATN_BorderStyle,
        C.XDW_ATN_FillColor,
        C.XDW_ATN_FillStyle,
        C.XDW_ATN_FillTransparent,
    )
    return {
        name: {
            "core": annotation.get_standard_attribute(name),
            "raw": annotation.get_standard_attribute_raw(name),
        }
        for name in names
    }


def _assert_rectangle_values(values):
    assert values[C.XDW_ATN_BorderColor]["core"] == Color.RED
    assert values[C.XDW_ATN_BorderWidth] == {"core": 2, "raw": 2}
    assert values[C.XDW_ATN_BorderStyle] == {"core": True, "raw": 1}
    assert values[C.XDW_ATN_FillColor]["core"] == Color.YELLOW
    assert values[C.XDW_ATN_FillStyle] == {"core": True, "raw": 1}
    assert values[C.XDW_ATN_FillTransparent] == {"core": False, "raw": 0}


def test_runtime_and_blank_fixture_preflight(api, blank_fixture_source: Path, evidence):
    with api.open_document(blank_fixture_source) as document:
        annotations = list(document.page(1).annotations())
        evidence(
            "preflight",
            runtime=api.diagnose(),
            pages=document.page_count,
            page_1_annotations=len(annotations),
        )
        assert document.page_count == 1, "DOCUWORKS_TEST_XDW must contain exactly one page"
        assert not annotations, "DOCUWORKS_TEST_XDW must have a blank first page"


def test_date_stamp_fixture_preflight(
    api, date_stamp_fixture_source: Path, evidence
):
    with api.open_document(date_stamp_fixture_source) as document:
        stamps = _annotations_in_document(document, AnnotationType.DATE_STAMP)
        first_page_number, _ = _first_in_document(
            document, AnnotationType.DATE_STAMP
        )
        evidence(
            "date_stamp_preflight",
            pages=document.page_count,
            date_stamp_count=len(stamps),
            first_date_stamp_page=first_page_number,
        )


def test_rectangle_six_attributes_roundtrip(api, xdw_copy, evidence):
    with api.open_document(xdw_copy, mode=OpenMode.UPDATE) as document:
        rectangle = document.page(1).add_rectangle(
            RectMM(20, 20, 30, 20),
            border_color=Color.RED,
            border_width=2,
            border_visible=True,
            fill_color=Color.YELLOW,
            fill_visible=True,
            fill_transparent=False,
        )
        evidence("call", operation="add_rectangle", handle=_handle_value(rectangle.handle))
        memory = _rectangle_values(rectangle)
        evidence("memory", values=memory)
        _assert_rectangle_values(memory)
        document.save()
    with api.open_document(xdw_copy) as document:
        rectangle = _latest(document.page(1), AnnotationType.RECTANGLE)
        persisted = _rectangle_values(rectangle)
        evidence("persistence", values=persisted)
        _assert_rectangle_values(persisted)


@pytest.mark.parametrize(
    ("text", "expected_text_type"),
    [
        pytest.param("ASCII", C.XDW_TEXT_MULTIBYTE, id="ascii"),
        # A W setter with UNICODE_IFNECESSARY may still be normalized to Unicode by
        # the installed product even when the text is representable in CP932.
        pytest.param("日本語", None, id="cp932-observe-storage"),
        pytest.param("😀", C.XDW_TEXT_UNICODE, id="outside-acp"),
    ],
)
def test_text_encoding_units_and_margin_roundtrip(
    api, xdw_copy, evidence, text, expected_text_type
):
    with api.open_document(xdw_copy, mode=OpenMode.UPDATE) as document:
        source_document_version = _document_version(document)
        annotation = document.page(1).add_text(
            PointMM(20, 20), text, font_size=12.0, fore_color=Color.BLUE
        )
        evidence(
            "call",
            operation="add_text",
            handle=_handle_value(annotation.handle),
            text=text,
            source_document_version=source_document_version,
        )
        annotation.set_standard_attribute(C.XDW_ATN_TextTopMargin, 1.7)
        memory = {
            "text": annotation.get_standard_attribute(C.XDW_ATN_Text),
            "text_type": _text_type(annotation, C.XDW_ATN_Text),
            "font_size_core": annotation.get_standard_attribute(C.XDW_ATN_FontSize),
            "font_size_raw": annotation.get_standard_attribute_raw(C.XDW_ATN_FontSize),
            "margin_core": annotation.get_standard_attribute(C.XDW_ATN_TextTopMargin),
            "margin_raw": annotation.get_standard_attribute_raw(C.XDW_ATN_TextTopMargin),
            "document_version": _document_version(document),
        }
        evidence("memory", values=memory)
        assert {
            key: value
            for key, value in memory.items()
            if key not in {"text_type", "document_version"}
        } == {
            "text": text,
            "font_size_core": 12.0,
            "font_size_raw": 120,
            "margin_core": 1.7,
            "margin_raw": 170,
        }
        if expected_text_type is not None:
            assert memory["text_type"] == expected_text_type
        document.save()
    with api.open_document(xdw_copy) as document:
        annotation = _latest(document.page(1), AnnotationType.TEXT)
        persisted = {
            "text": annotation.get_standard_attribute(C.XDW_ATN_Text),
            "text_type": _text_type(annotation, C.XDW_ATN_Text),
            "font_size_core": annotation.get_standard_attribute(C.XDW_ATN_FontSize),
            "font_size_raw": annotation.get_standard_attribute_raw(C.XDW_ATN_FontSize),
            "margin_core": annotation.get_standard_attribute(C.XDW_ATN_TextTopMargin),
            "margin_raw": annotation.get_standard_attribute_raw(C.XDW_ATN_TextTopMargin),
            "document_version": _document_version(document),
        }
        evidence("persistence", values=persisted)
        assert {
            key: value for key, value in persisted.items() if key != "document_version"
        } == {
            key: value for key, value in memory.items() if key != "document_version"
        }
        if text == "ASCII":
            assert persisted["document_version"] == source_document_version


def _custom_and_user_values(annotation):
    custom = {item.name: item for item in annotation.custom_attributes()}
    return {
        "custom": {
            "int": custom["int"],
            "string": custom["string"],
            "date": custom["date"],
            "bool": custom["bool"],
            "other": custom["other"],
        },
        "user_bytes": annotation.get_user_attribute("bytes"),
    }


def _assert_custom_and_user_values(values):
    custom = values["custom"]
    assert custom["int"].value == -12
    assert custom["string"].value == "確認"
    assert custom["date"].value == 123456789
    assert custom["bool"].value is True
    assert custom["other"].value is None
    assert values["user_bytes"] == b"\x00\x01\xff"


def test_custom_and_user_attributes_roundtrip(api, xdw_copy, evidence):
    with api.open_document(xdw_copy, mode=OpenMode.UPDATE) as document:
        annotation = document.page(1).add_rectangle(RectMM(20, 20, 30, 20))
        evidence("call", operation="add_rectangle", handle=_handle_value(annotation.handle))
        annotation.set_custom_attribute("int", CustomAttributeKind.INT, -12)
        annotation.set_custom_attribute("string", CustomAttributeKind.STRING, "確認")
        annotation.set_custom_attribute("date", CustomAttributeKind.DATE, 123456789)
        annotation.set_custom_attribute("bool", CustomAttributeKind.BOOL, True)
        annotation.set_custom_attribute("other", CustomAttributeKind.OTHER, None)
        annotation.set_user_attribute("bytes", b"\x00\x01\xff")
        memory = _custom_and_user_values(annotation)
        evidence("memory", values=memory)
        _assert_custom_and_user_values(memory)
        document.save()
    with api.open_document(xdw_copy) as document:
        annotation = _latest(document.page(1), AnnotationType.RECTANGLE)
        persisted = _custom_and_user_values(annotation)
        evidence("persistence", values=persisted)
        _assert_custom_and_user_values(persisted)


def _observe_user_get_modes(annotation, name: str):
    encoded_name = annotation.document.multibyte_encoding.encode(name)
    observations = []
    for mode, size, has_buffer in (
        ("null-size-0", 0, False),
        ("dummy-size-0", 0, True),
        ("buffer-size-1", 1, True),
    ):
        storage = ctypes.create_string_buffer(1) if has_buffer else None
        pointer = ctypes.cast(storage, ctypes.c_char_p) if storage is not None else None
        result = annotation.raw.XDW_GetAnnotationUserAttribute(
            annotation.handle,
            encoded_name,
            pointer,
            size,
            None,
        )
        signed = ctypes.c_int32(result).value
        observations.append(
            {
                "mode": mode,
                "buffer_non_null": has_buffer,
                "size": size,
                "result": signed,
                "unsigned_result": f"0x{ctypes.c_uint32(result).value:08X}",
                "symbol": C.ERROR_NAMES.get(signed),
                "byte_0": storage.raw[0] if storage is not None and signed >= 0 else None,
            }
        )
    return observations


def test_user_zero_byte_is_observation_only(api, xdw_copy, evidence):
    """Record the product contract without claiming retrievability.

    The non-NULL/size-zero setter call is distinct from deletion at the ctypes
    boundary.  Some product builds accept it but return XDW_E_UNEXPECTED from
    the getter, so this remains OBSERVE until the vendor contract is confirmed.
    """
    with api.open_document(xdw_copy, mode=OpenMode.UPDATE) as document:
        annotation = document.page(1).add_rectangle(RectMM(20, 20, 30, 20))
        annotation.set_user_attribute("empty", b"")
        memory = _observe_user_get_modes(annotation, "empty")
        evidence("observe_memory", setter_accepted=True, raw_get_modes=memory)
        document.save()
    with api.open_document(xdw_copy) as document:
        annotation = _latest(document.page(1), AnnotationType.RECTANGLE)
        persisted = _observe_user_get_modes(annotation, "empty")
        evidence("observe_persistence", setter_accepted=True, raw_get_modes=persisted)
    # OBSERVE only: getter success is deliberately not a pass criterion.


def _try_raw_string_set(annotation, name: str, value: str, *, unicode: bool) -> int:
    if unicode:
        storage = wchar_buffer(value)
        result = annotation.raw.XDW_SetAnnotationAttributeW(
            annotation.document.handle,
            annotation.handle,
            name.encode("ascii"),
            C.XDW_ATYPE_STRING,
            ctypes.cast(storage, ctypes.c_void_p),
            C.XDW_TEXT_UNICODE_IFNECESSARY,
            annotation.document.multibyte_encoding.codepage,
            0,
            None,
        )
    else:
        data = annotation.document.multibyte_encoding.encode(value)
        storage = ctypes.create_string_buffer(data + b"\0")
        result = annotation.raw.XDW_SetAnnotationAttribute(
            annotation.document.handle,
            annotation.handle,
            name.encode("ascii"),
            C.XDW_ATYPE_STRING,
            ctypes.cast(storage, ctypes.c_char_p),
            0,
            None,
        )
    return ctypes.c_int32(result).value


@pytest.mark.parametrize(
    ("name", "value", "unicode"),
    [
        pytest.param(C.XDW_ATN_DateFormat, "yy.mm.dd", False, id="date-lower"),
        pytest.param(C.XDW_ATN_DateFormat, "yy.MM.dd", False, id="date-upper"),
        pytest.param(C.XDW_ATN_TopField, "日" * 6, True, id="top-japanese-6"),
        pytest.param(C.XDW_ATN_TopField, "日" * 7, True, id="top-japanese-7"),
        pytest.param(C.XDW_ATN_TopField, "A" * 12, True, id="top-ascii-12"),
        pytest.param(C.XDW_ATN_TopField, "A" * 13, True, id="top-ascii-13"),
    ],
)
def test_date_stamp_probe_is_observation_only(
    api, date_xdw_copy, evidence, name, value, unicode
):
    accepted = False
    memory = None
    with api.open_document(date_xdw_copy, mode=OpenMode.UPDATE) as document:
        page_number, stamp = _first_in_document(document, AnnotationType.DATE_STAMP)
        before = stamp.get_standard_attribute_raw(name)
        result = _try_raw_string_set(stamp, name, value, unicode=unicode)
        accepted = result >= 0
        if accepted:
            memory = stamp.get_standard_attribute_raw(name)
            document.save()
        evidence(
            "observe_call",
            attribute=name,
            input=value,
            page_number=page_number,
            before=before,
            result=result,
            accepted=accepted,
            memory_get=memory,
        )
    persisted = None
    if accepted:
        with api.open_document(date_xdw_copy) as document:
            persisted_page_number, stamp = _first_in_document(
                document, AnnotationType.DATE_STAMP
            )
            persisted = stamp.get_standard_attribute_raw(name)
            assert persisted_page_number == page_number
    evidence(
        "observe_persistence",
        attribute=name,
        input=value,
        accepted=accepted,
        memory_get=memory,
        persistence_get=persisted,
    )
    # OBSERVE only: acceptance and equality remain evidence, not pass criteria.


def test_straight_line_points_and_attributes_roundtrip(api, xdw_copy, evidence):
    names = (
        C.XDW_ATN_BorderWidth,
        C.XDW_ATN_BorderColor,
        C.XDW_ATN_BorderTransparent,
        C.XDW_ATN_ArrowheadType,
        C.XDW_ATN_ArrowheadStyle,
        C.XDW_ATN_BorderType,
    )
    with api.open_document(xdw_copy, mode=OpenMode.UPDATE) as document:
        line = document.page(1).add_line(
            PointMM(20, 20),
            PointMM(50, 40),
            border_width=2,
            border_color=Color.BLUE,
            border_transparent=False,
            border_type=BorderType.DASH,
            arrowhead_type=ArrowheadType.ENDING,
            arrowhead_style=ArrowheadStyle.POLYGON,
        )
        memory = {name: line.get_standard_attribute_raw(name) for name in names}
        memory["points_raw"] = line.get_standard_attribute_raw(C.XDW_ATN_Points)
        memory["points"] = line.get_standard_attribute(C.XDW_ATN_Points)
        evidence("memory", values=memory)
        assert memory["points_raw"] == (RawPoint(2000, 2000), RawPoint(3000, 2000))
        assert memory["points"] == (PointMM(20, 20), PointMM(50, 40))
        document.save()
    with api.open_document(xdw_copy) as document:
        line = _latest(document.page(1), AnnotationType.STRAIGHT_LINE)
        persisted = {name: line.get_standard_attribute_raw(name) for name in names}
        persisted["points_raw"] = line.get_standard_attribute_raw(C.XDW_ATN_Points)
        persisted["points"] = line.get_standard_attribute(C.XDW_ATN_Points)
        evidence("persistence", values=persisted)
        assert persisted == memory


def test_sticky_and_ellipse_roundtrip(api, xdw_copy, evidence):
    with api.open_document(xdw_copy, mode=OpenMode.UPDATE) as document:
        page = document.page(1)
        sticky = page.add_sticky(
            PointMM(15, 15),
            SizeMM(35, 30),
            fill_color=Color.STICKY_YELLOW,
            auto_resize=False,
            text="付箋",
        )
        ellipse = page.add_ellipse(
            RectMM(70, 20, 30, 20),
            border_color=Color.RED,
            border_width=2,
            border_visible=True,
            fill_color=Color.YELLOW,
            fill_visible=True,
            fill_transparent=False,
        )
        memory = {
            "sticky_color": sticky.get_standard_attribute_raw(C.XDW_ATN_FillColor),
            "sticky_auto": sticky.get_standard_attribute_raw(C.XDW_ATN_AutoResize),
            "sticky_children": len(list(sticky.descendants())),
            "ellipse": _rectangle_values(ellipse),
        }
        evidence("memory", values=memory)
        document.save()
    with api.open_document(xdw_copy) as document:
        page = document.page(1)
        sticky = _latest(page, AnnotationType.STICKY)
        ellipse = _latest(page, AnnotationType.ELLIPSE)
        persisted = {
            "sticky_color": sticky.get_standard_attribute_raw(C.XDW_ATN_FillColor),
            "sticky_auto": sticky.get_standard_attribute_raw(C.XDW_ATN_AutoResize),
            "sticky_children": len(list(sticky.descendants())),
            "ellipse": _rectangle_values(ellipse),
        }
        evidence("persistence", values=persisted)
        assert persisted == memory


def test_polygon_and_marker_points_roundtrip(api, xdw_copy, evidence):
    polygon_points = (PointMM(20, 20), PointMM(50, 20), PointMM(40, 45))
    marker_points = (PointMM(70, 20), PointMM(90, 30), PointMM(75, 45))
    with api.open_document(xdw_copy, mode=OpenMode.UPDATE) as document:
        page = document.page(1)
        polygon = page.add_polygon(
            polygon_points,
            close=True,
            border_color=Color.BLUE,
            border_width=2,
            border_visible=True,
            fill_color=Color.YELLOW,
            fill_visible=True,
            fill_transparent=False,
            arrowhead_type=ArrowheadType.NONE,
            arrowhead_style=ArrowheadStyle.WIDE_POLYLINE,
        )
        marker = page.add_marker(
            marker_points,
            border_color=Color.GREEN,
            border_width=3,
            border_transparent=False,
        )
        memory = {
            "polygon": polygon.get_standard_attribute(C.XDW_ATN_Points),
            "polygon_raw": polygon.get_standard_attribute_raw(C.XDW_ATN_Points),
            "marker": marker.get_standard_attribute(C.XDW_ATN_Points),
            "marker_raw": marker.get_standard_attribute_raw(C.XDW_ATN_Points),
        }
        evidence("memory", values=memory)
        assert memory["polygon"] == polygon_points
        assert memory["marker"] == marker_points
        document.save()
    with api.open_document(xdw_copy) as document:
        page = document.page(1)
        polygon = _latest(page, AnnotationType.POLYGON)
        marker = _latest(page, AnnotationType.MARKER)
        persisted = {
            "polygon": polygon.get_standard_attribute(C.XDW_ATN_Points),
            "polygon_raw": polygon.get_standard_attribute_raw(C.XDW_ATN_Points),
            "marker": marker.get_standard_attribute(C.XDW_ATN_Points),
            "marker_raw": marker.get_standard_attribute_raw(C.XDW_ATN_Points),
        }
        evidence("persistence", values=persisted)
        assert persisted == memory


@pytest.mark.parametrize(
    ("link_type", "target", "attribute"),
    [
        (LinkType.URL, "https://example.com/", C.XDW_ATN_Url),
        (LinkType.XDW, r"C:\example\linked-document.xdw", C.XDW_ATN_XdwPath),
        (LinkType.OTHER_FILE, r"C:\Windows\notepad.exe", C.XDW_ATN_OtherFilePath),
        (LinkType.MAIL_ADDRESS, "nobody@example.invalid", C.XDW_ATN_MailAddress),
    ],
)
def test_link_type_roundtrip(api, xdw_copy, evidence, link_type, target, attribute):
    with api.open_document(xdw_copy, mode=OpenMode.UPDATE) as document:
        link = document.page(1).add_link(
            PointMM(20, 20),
            link_type.name,
            link_type=link_type,
            target=target,
            auto_resize=False,
            size=SizeMM(40, 15),
            fore_color=Color.BLUE,
            font_size=12,
        )
        memory = {
            "caption": link.get_standard_attribute(C.XDW_ATN_Caption),
            "type": link.get_standard_attribute_raw(C.XDW_ATN_LinkType),
            "target": link.get_standard_attribute(attribute),
        }
        evidence("memory", values=memory)
        document.save()
    with api.open_document(xdw_copy) as document:
        link = _latest(document.page(1), AnnotationType.LINK)
        persisted = {
            "caption": link.get_standard_attribute(C.XDW_ATN_Caption),
            "type": link.get_standard_attribute_raw(C.XDW_ATN_LinkType),
            "target": link.get_standard_attribute(attribute),
        }
        evidence("persistence", values=persisted)
        assert persisted == memory


def test_simple_api_delegates_to_core_and_persists(xdw_copy, evidence):
    with open_xdw(xdw_copy, writable=True, codepage=932) as document:
        page = document.page()
        transient = page.text("Delete me", x=20, y=20, font_size=12)
        rectangle = page.rectangle(x=20, y=40, width=30, height=20)
        sticky = page.sticky(
            x=70,
            y=40,
            width=30,
            height=30,
            fill_color=Color.STICKY_YELLOW,
            text="Simple child",
        )
        assert all(
            isinstance(annotation, SimpleAnnotation)
            for annotation in (transient, rectangle, sticky)
        )
        top_level = page.annotations()
        recursive = page.annotations(recursive=True)
        assert len(recursive) == len(top_level) + 1
        assert recursive[-1].type == AnnotationType.TEXT
        rectangle.move_to(x=25, y=45)
        rectangle.resize(width=35, height=25)
        assert rectangle.position == PointMM(25, 45)
        assert rectangle.size == SizeMM(35, 25)
        transient.delete()
        with pytest.raises(ClosedHandleError):
            _ = transient.type
        document.save()
    with open_xdw(xdw_copy, codepage=932) as document:
        page = document.page()
        top_level = page.annotations()
        recursive = page.annotations(recursive=True)
        assert [annotation.type for annotation in top_level] == [
            AnnotationType.RECTANGLE,
            AnnotationType.STICKY,
        ]
        assert [annotation.type for annotation in recursive] == [
            AnnotationType.RECTANGLE,
            AnnotationType.STICKY,
            AnnotationType.TEXT,
        ]
        rectangle = top_level[0]
        assert rectangle.position == PointMM(25, 45)
        assert rectangle.size == SizeMM(35, 25)
        with pytest.raises(ReadOnlyDocumentError):
            rectangle.move_to(x=30, y=50)
        evidence(
            "persistence",
            simple_api=True,
            top_level_types=[int(annotation.type) for annotation in top_level],
            recursive_types=[int(annotation.type) for annotation in recursive],
            rectangle_position=rectangle.position,
            rectangle_size=rectangle.size,
        )


def test_simple_enumerates_existing_date_stamp_without_creation_api(
    date_xdw_copy, evidence
):
    with open_xdw(date_xdw_copy, codepage=932) as document:
        stamps = [
            annotation
            for page_number in range(1, document.core.page_count + 1)
            for annotation in document.page(page_number).annotations(recursive=True)
            if annotation.type == AnnotationType.DATE_STAMP
        ]
        assert stamps
        assert all(isinstance(annotation, SimpleAnnotation) for annotation in stamps)
        assert not hasattr(document.page(1), "date_stamp")
        evidence("observation", simple_date_stamp_count=len(stamps))


def _coverage_annotation(document, annotation_type):
    page = document.page(1)
    if annotation_type == C.XDW_AID_TEXT:
        return page.add_text(PointMM(20, 20), "Coverage", font_size=12)
    if annotation_type == C.XDW_AID_LINK:
        return page.add_link(
            PointMM(20, 20),
            "Coverage",
            link_type=LinkType.THIS_DOCUMENT,
        )
    if annotation_type == C.XDW_AID_FUSEN:
        return page.add_sticky(PointMM(20, 20), SizeMM(30, 30))
    if annotation_type == C.XDW_AID_STRAIGHTLINE:
        return page.add_line(PointMM(20, 20), PointMM(50, 40))
    if annotation_type == C.XDW_AID_RECTANGLE:
        return page.add_rectangle(RectMM(20, 20, 30, 20))
    if annotation_type == C.XDW_AID_ARC:
        return page.add_ellipse(RectMM(20, 20, 30, 20))
    if annotation_type == C.XDW_AID_STAMP:
        return _first_in_document(document, AnnotationType.DATE_STAMP)[1]
    if annotation_type == C.XDW_AID_MARKER:
        return page.add_marker((PointMM(20, 20), PointMM(50, 40)))
    if annotation_type == C.XDW_AID_POLYGON:
        return page.add_polygon(
            (PointMM(20, 20), PointMM(50, 20), PointMM(40, 45)), close=True
        )
    raise AssertionError(f"unsupported coverage annotation type: {annotation_type}")


def _ensure_raw_condition(annotation, name, value):
    condition_spec = STANDARD_ATTRIBUTE_REGISTRY[(int(annotation.annotation_type), name)]
    for parent in condition_spec.conditions:
        _ensure_raw_condition(annotation, parent.attribute_name, parent.equals)
    annotation.set_standard_attribute_raw(name, value)


def _prepare_runtime_condition(annotation, name):
    link_conditions = {
        C.XDW_ATN_Url: C.XDW_LT_LINK_TO_URL,
        C.XDW_ATN_XdwPath: C.XDW_LT_LINK_TO_XDW,
        C.XDW_ATN_XdwPath_Relative: C.XDW_LT_LINK_TO_XDW,
        C.XDW_ATN_XdwLink: C.XDW_LT_LINK_TO_XDW,
        C.XDW_ATN_PageFrom: C.XDW_LT_LINK_TO_XDW,
        C.XDW_ATN_XdwNameInXbd: C.XDW_LT_LINK_TO_XDW,
        C.XDW_ATN_XdwPage: C.XDW_LT_LINK_TO_XDW,
        C.XDW_ATN_OtherFilePath: C.XDW_LT_LINK_TO_OTHERFILE,
        C.XDW_ATN_OtherFilePath_Relative: C.XDW_LT_LINK_TO_OTHERFILE,
        C.XDW_ATN_MailAddress: C.XDW_LT_LINK_TO_MAILADDR,
    }
    if name in link_conditions:
        _ensure_raw_condition(annotation, C.XDW_ATN_LinkType, link_conditions[name])
    if name in {
        C.XDW_ATN_DateField_FirstChar,
        C.XDW_ATN_YearField,
        C.XDW_ATN_MonthField,
        C.XDW_ATN_DayField,
        C.XDW_ATN_DateOrder,
    }:
        _ensure_raw_condition(annotation, C.XDW_ATN_DateStyle, C.XDW_STAMP_MANUAL)


def _coverage_raw_value(spec):
    strings = {
        C.XDW_ATN_Text: "Coverage",
        C.XDW_ATN_Caption: "Coverage",
        C.XDW_ATN_FontName: "Arial",
        C.XDW_ATN_Tooltip_String: "Coverage tooltip",
        C.XDW_ATN_Url: "https://example.com/",
        C.XDW_ATN_XdwPath: r"C:\example\linked-document.xdw",
        C.XDW_ATN_XdwNameInXbd: "document.xdw",
        C.XDW_ATN_LinkAtn_Title: "Coverage title",
        C.XDW_ATN_OtherFilePath: r"C:\Windows\notepad.exe",
        C.XDW_ATN_MailAddress: "nobody@example.invalid",
        C.XDW_ATN_TopField: "A",
        C.XDW_ATN_BottomField: "B",
        C.XDW_ATN_DateField_FirstChar: "'",
        C.XDW_ATN_YearField: "2026",
        C.XDW_ATN_MonthField: "8",
        C.XDW_ATN_DayField: "31",
        C.XDW_ATN_DateFormat: "yy.mm.dd",
    }
    if spec.storage_kind == "string":
        if spec.name in strings:
            return strings[spec.name]
        if spec.allowed_values:
            return sorted(spec.allowed_values)[0]
        return "A"
    if spec.allowed_values:
        values = sorted(int(value) for value in spec.allowed_values)
        if spec.python_kind == "bool":
            return 1
        if spec.name in {C.XDW_ATN_LinkType, C.XDW_ATN_PageFrom}:
            return 0
        return next((value for value in values if value >= 0), values[0])
    if spec.minimum is not None:
        return int(spec.minimum)
    return 1


_COVERAGE_KEYS = sorted(
    STANDARD_ATTRIBUTE_REGISTRY,
    key=lambda item: (int(item[0]), item[1]),
)


@pytest.mark.parametrize(
    ("annotation_type", "attribute_name"),
    _COVERAGE_KEYS,
    ids=[f"{annotation_type}-{name.lstrip('%')}" for annotation_type, name in _COVERAGE_KEYS],
)
def test_standard_registry_pair_persistence(
    request,
    api,
    blank_fixture_source,
    date_stamp_fixture_source,
    evidence_writer,
    evidence,
    annotation_type,
    attribute_name,
):
    spec = STANDARD_ATTRIBUTE_REGISTRY[(annotation_type, attribute_name)]
    source = (
        date_stamp_fixture_source
        if annotation_type == C.XDW_AID_STAMP
        else blank_fixture_source
    )
    xdw_path = evidence_writer.copy_fixture(source, request.node.name)
    with api.open_document(xdw_path, mode=OpenMode.UPDATE) as document:
        annotation = _coverage_annotation(document, annotation_type)
        _prepare_runtime_condition(annotation, attribute_name)
        for condition in spec.conditions:
            _ensure_raw_condition(annotation, condition.attribute_name, condition.equals)
        if spec.writable:
            requested = _coverage_raw_value(spec)
            annotation.set_standard_attribute_raw(attribute_name, requested)
        immediate = annotation.get_standard_attribute_raw(attribute_name)
        evidence(
            "coverage_immediate",
            annotation_type=annotation_type,
            attribute=attribute_name,
            writable=spec.writable,
            value=immediate,
        )
        document.save()
    with api.open_document(xdw_path) as document:
        annotation = _coverage_annotation_for_read(document, annotation_type)
        persisted = annotation.get_standard_attribute_raw(attribute_name)
        evidence(
            "coverage_persistence",
            annotation_type=annotation_type,
            attribute=attribute_name,
            writable=spec.writable,
            value=persisted,
        )
        assert persisted == immediate


def _coverage_annotation_for_read(document, annotation_type):
    if annotation_type == C.XDW_AID_STAMP:
        return _first_in_document(document, AnnotationType.DATE_STAMP)[1]
    return _latest(document.page(1), AnnotationType(annotation_type))
