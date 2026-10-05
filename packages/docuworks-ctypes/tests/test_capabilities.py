import ctypes
from pathlib import Path

import pytest

from docuworks_ctypes._raw import constants as C
from docuworks_ctypes._raw import types as T
from docuworks_ctypes.capabilities import annotation_capability, validate_annotation_size
from docuworks_ctypes.document import Annotation, Document, Page
from docuworks_ctypes.encoding import MultibyteEncodingPolicy
from docuworks_ctypes.enums import OpenMode
from docuworks_ctypes.geometry import RectMM, SizeMM


@pytest.mark.parametrize(
    ("kind", "minimum", "maximum"),
    [
        (C.XDW_AID_RECTANGLE, 3, 2400),
        (C.XDW_AID_ARC, 3, 2400),
        (C.XDW_AID_TEXT, 5, 2400),
        (C.XDW_AID_BITMAP, 5, 2400),
        (C.XDW_AID_LINK, 5, 2400),
        (C.XDW_AID_FUSEN, 5, 500),
        (C.XDW_AID_STAMP, 10, 500),
    ],
)
def test_size_boundaries(kind, minimum, maximum):
    spec = annotation_capability(kind)
    validate_annotation_size(spec, SizeMM(minimum, minimum))
    validate_annotation_size(spec, SizeMM(maximum, maximum))
    with pytest.raises(ValueError):
        validate_annotation_size(spec, SizeMM(minimum - 0.01, minimum))
    with pytest.raises(ValueError):
        validate_annotation_size(spec, SizeMM(maximum + 0.01, maximum))


def test_date_stamp_height_is_normalized_to_width():
    normalized = validate_annotation_size(
        annotation_capability(C.XDW_AID_STAMP), SizeMM(20, 100)
    )
    assert normalized == SizeMM(20, 20)


def test_non_resizable_annotation_is_rejected():
    with pytest.raises(ValueError):
        validate_annotation_size(
            annotation_capability(C.XDW_AID_STRAIGHTLINE), SizeMM(10, 10)
        )


def test_resize_conditions_are_strict():
    text = annotation_capability(C.XDW_AID_TEXT)
    validate_annotation_size(
        text,
        SizeMM(10, 10),
        context={C.XDW_ATN_WordWrap: 1, C.XDW_ATN_TextOrientation: 0},
    )
    with pytest.raises(ValueError):
        validate_annotation_size(
            text,
            SizeMM(10, 10),
            context={C.XDW_ATN_WordWrap: 0, C.XDW_ATN_TextOrientation: 0},
        )
    link = annotation_capability(C.XDW_AID_LINK)
    with pytest.raises(ValueError):
        validate_annotation_size(
            link, SizeMM(10, 10), context={C.XDW_ATN_AutoResize: 1}
        )


class ResizeRaw:
    def __init__(self, values):
        self.values = values
        self.size_args = None

    def XDW_GetAnnotationAttributeW(self, *args):
        value = self.values[args[1].decode("ascii")]
        data = int(value).to_bytes(4, "little", signed=True)
        if args[2] is None:
            return 4
        ctypes.memmove(args[2], data, 4)
        return 4

    def XDW_SetAnnotationSize(self, *args):
        self.size_args = args
        return 0


def _annotation(kind, raw, width=1000, height=1000):
    document = Document(
        raw,
        1,
        Path("fixture.xdw"),
        OpenMode.UPDATE,
        MultibyteEncodingPolicy.create(932),
    )
    page = Page(document, 1)
    info = T.XDW_ANNOTATION_INFO()
    info.handle = 2
    info.nAnnotationType = kind
    info.nWidth = width
    info.nHeight = height
    return Annotation(page, info)


def test_annotation_set_size_checks_text_state_before_raw_call():
    raw = ResizeRaw({C.XDW_ATN_WordWrap: 1, C.XDW_ATN_TextOrientation: 0})
    annotation = _annotation(C.XDW_AID_TEXT, raw)
    annotation.set_size(SizeMM(12.5, 20))
    assert raw.size_args[2:4] == (1250, 2000)


def test_annotation_set_size_normalizes_date_stamp_height():
    raw = ResizeRaw({})
    annotation = _annotation(C.XDW_AID_STAMP, raw)
    annotation.set_size(SizeMM(20, 99))
    assert raw.size_args[2:4] == (2000, 2000)


def test_add_rectangle_validates_before_calling_xdwapi():
    class NoAddRaw:
        called = False

        def XDW_AddAnnotation(self, *args):
            self.called = True
            return 0

    raw = NoAddRaw()
    document = Document(raw, 1, Path("fixture.xdw"), OpenMode.UPDATE)
    with pytest.raises(ValueError):
        Page(document, 1).add_rectangle(RectMM(1, 1, 2.99, 10))
    assert raw.called is False
