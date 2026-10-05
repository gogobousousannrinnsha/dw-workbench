import ctypes
from pathlib import Path

import pytest

from docuworks_ctypes._raw import constants as C
from docuworks_ctypes._raw import types as T
from docuworks_ctypes.document import Annotation, Document, Page
from docuworks_ctypes.encoding import MultibyteEncodingPolicy
from docuworks_ctypes.enums import AnnotationType, OpenMode
from docuworks_ctypes.errors import AnnotationRefreshError
from docuworks_ctypes.geometry import PointMM


class AddRaw:
    def __init__(self, *, returned_handle=99, enumerated_handle=99):
        self.returned_handle = returned_handle
        self.enumerated_handle = enumerated_handle
        self.parent_handle_seen = None

    @staticmethod
    def _write_handle(pointer, value):
        ctypes.cast(pointer, ctypes.POINTER(T.XDW_ANNOTATION_HANDLE))[0] = value

    def XDW_AddAnnotation(self, *args):
        self._write_handle(args[6], self.returned_handle)
        return 0

    def XDW_AddAnnotationOnParentAnnotation(self, *args):
        self._write_handle(args[6], self.returned_handle)
        return 0

    def XDW_AddAnnotationFromAnnFileW(self, *args):
        self._write_handle(args[7], self.returned_handle)
        return 0

    def XDW_GetPageInformation(self, handle, page, info_pointer):
        info = ctypes.cast(info_pointer, ctypes.POINTER(T.XDW_PAGE_INFO)).contents
        info.nAnnotations = 1
        return 0

    def XDW_GetAnnotationInformation(
        self, handle, page, parent_handle, index, info_pointer, reserved
    ):
        self.parent_handle_seen = getattr(parent_handle, "value", parent_handle)
        info = ctypes.cast(info_pointer, ctypes.POINTER(T.XDW_ANNOTATION_INFO)).contents
        info.handle = self.enumerated_handle
        info.nAnnotationType = C.XDW_AID_TEXT
        info.nHorPos = 4321
        info.nVerPos = 8765
        info.nWidth = 111
        info.nHeight = 222
        info.nChildAnnotations = 0
        return 0


def _page(raw):
    document = Document(
        raw,
        1,
        Path("fixture.xdw"),
        OpenMode.UPDATE,
        MultibyteEncodingPolicy.create(932),
    )
    return Page(document, 1)


def test_top_level_add_returns_official_annotation_info():
    page = _page(AddRaw())
    annotation = page._add(AnnotationType.TEXT, PointMM(1, 2))
    assert annotation.handle_value == 99
    assert annotation._info.nHorPos == 4321
    assert annotation._info.nWidth == 111


def test_parent_add_enumerates_expected_new_child_and_updates_count():
    raw = AddRaw()
    page = _page(raw)
    parent_info = T.XDW_ANNOTATION_INFO()
    parent_info.handle = 50
    parent_info.nAnnotationType = C.XDW_AID_FUSEN
    parent_info.nChildAnnotations = 0
    parent = Annotation(page, parent_info)
    annotation = page._add(AnnotationType.TEXT, PointMM(1, 2), parent=parent)
    assert annotation.handle_value == 99
    assert raw.parent_handle_seen == 50
    assert parent._info.nChildAnnotations == 1


def test_ann_add_uses_the_same_refresh_path(tmp_path):
    ann = tmp_path / "sample.ann"
    ann.write_bytes(b"fixture")
    page = _page(AddRaw())
    annotation = page.add_from_ann(ann, PointMM(1, 2))
    assert annotation.handle_value == 99
    assert annotation._info.nVerPos == 8765


def test_handle_mismatch_raises_without_synthetic_fallback():
    page = _page(AddRaw(returned_handle=99, enumerated_handle=100))
    with pytest.raises(AnnotationRefreshError):
        page._add(AnnotationType.TEXT, PointMM(1, 2))
