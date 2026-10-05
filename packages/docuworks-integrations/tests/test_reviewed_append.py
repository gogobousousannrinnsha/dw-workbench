"""Append hints must never substitute invented geometry or an unrelated handle."""
import ctypes
from pathlib import Path

import pytest
from docuworks_ctypes._raw import constants as C, types as T
from docuworks_ctypes.document import Document, Page
from docuworks_ctypes.encoding import MultibyteEncodingPolicy
from docuworks_ctypes.enums import AnnotationType, OpenMode
from docuworks_ctypes.errors import AnnotationRefreshError, XdwError
from docuworks_ctypes.geometry import PointMM
from docuworks_integrations._reviewed_sdk import _BlankReviewPage


class Raw:
    def __init__(self, *, prepend=False, existing=(), omit=False, info_error=None):
        self.handles=list(existing)
        self.prepend=prepend
        self.omit=omit
        self.info_error=info_error
        self.page_reads=0
        self.indices=[]
        self.serial=100

    def XDW_GetPageInformation(self, doc, page, output):
        self.page_reads+=1
        ctypes.cast(output,ctypes.POINTER(T.XDW_PAGE_INFO)).contents.nAnnotations=len(self.handles)
        return 0

    def XDW_AddAnnotation(self, doc, kind, page, x, y, initial, output, reserved):
        self.serial+=1
        ctypes.cast(output,ctypes.POINTER(T.XDW_ANNOTATION_HANDLE))[0]=self.serial
        if not self.omit:
            self.handles.insert(0,self.serial) if self.prepend else self.handles.append(self.serial)
        return 0

    def XDW_GetAnnotationInformation(self, doc, page, parent, index, output, reserved):
        self.indices.append(index)
        if self.info_error is not None:return self.info_error
        if index>len(self.handles):return C.XDW_E_INVALIDARG
        info=ctypes.cast(output,ctypes.POINTER(T.XDW_ANNOTATION_INFO)).contents
        info.handle=self.handles[index-1]
        info.nAnnotationType=int(AnnotationType.TEXT)
        info.nHorPos=4321;info.nVerPos=8765;info.nWidth=111;info.nHeight=222
        return 0


def page(raw):
    doc=Document(raw,1,Path('synthetic.xdw'),OpenMode.UPDATE,MultibyteEncodingPolicy.create(932))
    return _BlankReviewPage(Page(doc,1))


def add(p):
    return p._add(AnnotationType.TEXT,PointMM(1,2))


def test_append_reads_count_once_and_preserves_real_info():
    raw=Raw();p=page(raw)
    actual=[add(p) for _ in range(3)]
    assert [a.handle_value for a in actual]==[101,102,103]
    assert all(a._info.nHorPos==4321 and a._info.nWidth==111 for a in actual)
    assert raw.page_reads==1 and raw.indices==[1,2,3]


def test_non_append_order_falls_back_and_disables_hint():
    raw=Raw(prepend=True);p=page(raw)
    assert [add(p).handle_value for _ in range(3)]==[101,102,103]
    assert raw.indices==[1,2,1,1]
    assert raw.page_reads==3 and p._next_index is None


def test_nonblank_page_uses_core_search():
    raw=Raw(existing=[77]);p=page(raw)
    assert add(p).handle_value==101
    assert raw.indices==[1,2] and raw.page_reads==2


def test_stale_index_invalidarg_falls_back():
    raw=Raw();p=page(raw);add(p)
    raw.handles.clear()
    assert add(p).handle_value==102
    assert raw.indices==[1,2,1] and p._next_index is None


def test_missing_returned_handle_fails_without_fake_annotation():
    raw=Raw(omit=True);p=page(raw)
    with pytest.raises(AnnotationRefreshError):add(p)


def test_other_native_error_is_not_hidden_by_fallback():
    raw=Raw(info_error=C.XDW_E_UNEXPECTED);p=page(raw)
    with pytest.raises(XdwError) as caught:add(p)
    assert caught.value.result==C.XDW_E_UNEXPECTED
    assert raw.page_reads==1 and raw.indices==[1]
