"""The rectangle consumer reuses counts without weakening handle validation."""
import ctypes
from pathlib import Path

import pytest
from docuworks_ctypes._raw import constants as C, types as T
from docuworks_ctypes.document import Document, Page
from docuworks_ctypes.encoding import MultibyteEncodingPolicy
from docuworks_ctypes.enums import AnnotationType, OpenMode
from docuworks_ctypes.errors import AnnotationRefreshError, XdwError
from docuworks_ctypes.geometry import PointMM
from docuworks_integrations._rectangle_sdk import _RectangleAppendPage


class Raw:
    def __init__(self, existing=(), *, omit=False, info_error=None):
        self.handles = list(existing)
        self.omit = omit
        self.info_error = info_error
        self.page_reads = 0
        self.serial = 100

    def XDW_GetPageInformation(self, doc, page, output):
        self.page_reads += 1
        ctypes.cast(output, ctypes.POINTER(T.XDW_PAGE_INFO)).contents.nAnnotations = len(self.handles)
        return 0

    def XDW_AddAnnotation(self, doc, kind, page, x, y, initial, output, reserved):
        self.serial += 1
        ctypes.cast(output, ctypes.POINTER(T.XDW_ANNOTATION_HANDLE))[0] = self.serial
        if not self.omit:
            self.handles.append(self.serial)
        return 0

    def XDW_GetAnnotationInformation(self, doc, page, parent, index, output, reserved):
        if self.info_error is not None:
            return self.info_error
        if index > len(self.handles):
            return C.XDW_E_INVALIDARG
        info = ctypes.cast(output, ctypes.POINTER(T.XDW_ANNOTATION_INFO)).contents
        info.handle = self.handles[index - 1]
        info.nAnnotationType = int(AnnotationType.RECTANGLE)
        info.nHorPos = 4321
        info.nVerPos = 8765
        info.nWidth = 111
        info.nHeight = 222
        return 0


def core_page(raw):
    return Page(Document(raw, 1, Path('synthetic.xdw'), OpenMode.UPDATE,
                         MultibyteEncodingPolicy.create(932)), 1)


def add(page):
    return page._add(AnnotationType.RECTANGLE, PointMM(1, 2))


@pytest.mark.parametrize('existing', [(), (77, 78)])
def test_append_preserves_existing_handles_and_actual_sdk_geometry(existing):
    raw = Raw(existing)
    page = _RectangleAppendPage(core_page(raw), len(existing))
    annotations = [add(page) for _ in range(3)]
    assert [a.handle_value for a in annotations] == [101, 102, 103]
    assert raw.handles[:len(existing)] == list(existing)
    assert all(a.position.x == 43.21 and a.size.width == 1.11 for a in annotations)
    assert raw.page_reads == 0


def test_additional_unexpected_annotation_falls_back_permanently():
    raw = Raw()
    page = _RectangleAppendPage(core_page(raw), 0)
    raw.handles.append(77)
    assert add(page).handle_value == 101
    assert raw.page_reads == 1 and page._annotation_count is None
    assert add(page).handle_value == 102
    assert raw.page_reads == 2


def test_invalidarg_disables_reuse_and_uses_normal_search(monkeypatch):
    raw = Raw()
    page = _RectangleAppendPage(core_page(raw), 0)
    original = raw.XDW_GetAnnotationInformation
    def invalid_once(*args):
        monkeypatch.setattr(raw, 'XDW_GetAnnotationInformation', original)
        return C.XDW_E_INVALIDARG
    monkeypatch.setattr(raw, 'XDW_GetAnnotationInformation', invalid_once)
    assert add(page).handle_value == 101
    assert raw.page_reads == 1 and page._annotation_count is None
    assert add(page).handle_value == 102
    assert raw.page_reads == 2


def test_missing_returned_handle_still_fails():
    raw = Raw(omit=True)
    with pytest.raises(AnnotationRefreshError):
        add(_RectangleAppendPage(core_page(raw), 0))


def test_other_sdk_errors_propagate_without_retry():
    raw = Raw(info_error=C.XDW_E_UNEXPECTED)
    with pytest.raises(XdwError) as caught:
        add(_RectangleAppendPage(core_page(raw), 0))
    assert caught.value.result == C.XDW_E_UNEXPECTED
    assert raw.page_reads == 0


def test_regular_core_page_retains_original_behavior():
    raw = Raw()
    page = core_page(raw)
    assert [add(page).handle_value for _ in range(2)] == [101, 102]
    assert raw.page_reads == 2


def test_parent_request_disables_reuse_and_delegates(monkeypatch):
    page = _RectangleAppendPage(core_page(Raw()), 0)
    parent, expected = object(), object()
    calls = []
    def fallback(self, handle, *, parent=None):
        calls.append((handle, parent))
        return expected
    monkeypatch.setattr(Page, '_refresh_added_annotation', fallback)
    handle = T.XDW_ANNOTATION_HANDLE(123)
    assert page._refresh_added_annotation(handle, parent=parent) is expected
    assert calls == [(handle, parent)] and page._annotation_count is None
