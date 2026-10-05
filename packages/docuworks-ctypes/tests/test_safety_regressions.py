"""Independent expectations for the 1.0.1 safety fixes; no native DLL required."""
import ctypes
from pathlib import Path

import pytest

from docuworks_ctypes import XdwApi, PointMM, RawPoint, AnnotationType, LinkType
from docuworks_ctypes._raw import constants as C, types as T
from docuworks_ctypes.attributes import (
    _raw_to_python, standard_attribute_spec, set_standard_attribute_raw,
    set_custom_attribute, CustomAttributeKind, set_user_attribute,
)
from docuworks_ctypes.document import Document, Page, Annotation
from docuworks_ctypes.encoding import MultibyteEncodingPolicy, wchar_buffer
from docuworks_ctypes.enums import OpenMode, AuthMode
from docuworks_ctypes.errors import XdwError


class NoNative:
    def __getattr__(self, name):
        def fail(*args):
            raise AssertionError('unexpected native call: ' + name)
        return fail


def page(raw=None):
    return Page(Document(raw or NoNative(), 1, Path('fixture.xdw'), OpenMode.UPDATE,
                         MultibyteEncodingPolicy.create(932)), 1)


@pytest.mark.parametrize('kind', [C.XDW_AID_MARKER, C.XDW_AID_POLYGON])
def test_points_use_first_point_not_previous(kind):
    points = [PointMM(20,20), PointMM(50,20), PointMM(50,50), PointMM(10,10), PointMM(10,10)]
    raw = [(2000,2000),(3000,0),(3000,3000),(-1000,-1000),(-1000,-1000)]
    assert [(p.x,p.y) for p in Page._initial_point_array(points)] == raw
    spec = standard_attribute_spec(kind, C.XDW_ATN_Points)
    assert _raw_to_python(spec, tuple(RawPoint(*p) for p in raw)) == tuple(points)


@pytest.mark.parametrize('value', ['A'*256, '日'*128, '😀'*64, 'x\0y'])
def test_caption_rejected_before_creation_or_setter(value):
    p=page()
    with pytest.raises(ValueError): p.add_link(PointMM(10,10), value, link_type=LinkType.THIS_DOCUMENT)
    spec=standard_attribute_spec(C.XDW_AID_LINK, C.XDW_ATN_Caption)
    with pytest.raises(ValueError):
        set_standard_attribute_raw(p.raw,1,2,spec,value,encoding_policy=p.document.multibyte_encoding)


@pytest.mark.parametrize('value', ['', 'A'*255, '日'*127+'A', '😀'*63])
def test_caption_allowed_boundaries_are_not_truncated(value):
    class Raw:
        def XDW_SetAnnotationAttributeW(self,*args):
            assert ctypes.string_at(args[4],len(value.encode('utf-16-le'))+2)==value.encode('utf-16-le')+b'\0\0'
            return 0
    set_standard_attribute_raw(Raw(),1,2,standard_attribute_spec(C.XDW_AID_LINK,C.XDW_ATN_Caption),value,
                               encoding_policy=MultibyteEncodingPolicy.create(932))


@pytest.mark.parametrize('value', [-2147483649, 2147483648])
@pytest.mark.parametrize('kind', [CustomAttributeKind.INT, CustomAttributeKind.DATE])
def test_custom_int32_rejects_overflow(value,kind):
    with pytest.raises(ValueError):set_custom_attribute(NoNative(),1,2,'name',kind,value)


@pytest.mark.parametrize('value', [-2147483649, 2147483648])
def test_standard_int32_rejects_overflow(value):
    spec=standard_attribute_spec(C.XDW_AID_MARKER,C.XDW_ATN_BorderWidth)
    with pytest.raises(ValueError):set_standard_attribute_raw(NoNative(),1,2,spec,value)


@pytest.mark.parametrize('value', ['x\0y', '\0'])
def test_nul_names_strings_and_paths_rejected(value):
    with pytest.raises(ValueError):wchar_buffer(value)
    with pytest.raises(ValueError):MultibyteEncodingPolicy.create(932).encode(value)
    with pytest.raises(ValueError):set_custom_attribute(NoNative(),1,2,value,CustomAttributeKind.STRING,'ok')
    with pytest.raises(ValueError):page().add_text(PointMM(10,10),value)


def test_binary_user_attribute_keeps_embedded_nul():
    class Raw:
        def XDW_SetAnnotationUserAttribute(self,doc,handle,name,value,size,reserved):
            assert ctypes.string_at(value,size)==b'a\0b' and size==3
            return 0
    set_user_attribute(Raw(),1,2,'name',b'a\0b',encoding_policy=MultibyteEncodingPolicy.create(932))


@pytest.mark.parametrize('value', [2400.01,-2400.01,float('nan'),float('inf')])
def test_position_rejects_before_native(value):
    p=page()
    with pytest.raises(ValueError):p._add(AnnotationType.TEXT,PointMM(value,0))
    info=T.XDW_ANNOTATION_INFO();info.handle=2;info.nHorPos=100
    a=Annotation(p,info)
    with pytest.raises(ValueError):a.set_position(PointMM(value,0))
    assert a.position.x==1


@pytest.mark.parametrize('body_fails,close_fails', [(False,False),(True,False),(False,True),(True,True)])
def test_close_preserves_original_exception(body_fails,close_fails):
    class Raw:
        def XDW_CloseDocumentHandle(self,*args):return C.XDW_E_UNEXPECTED if close_fails else 0
    original=ValueError('original')
    try:
        with page(Raw()).document:
            if body_fails:raise original
    except Exception as error:
        if body_fails:assert error is original
        else:assert close_fails and isinstance(error,XdwError)
    else:assert not body_fails and not close_fails


def test_broken_exception_note_cannot_replace_body_error():
    class BrokenNote(ValueError):
        def add_note(self,*args):raise RuntimeError('note failed')
    class Raw:
        def XDW_CloseDocumentHandle(self,*args):return C.XDW_E_UNEXPECTED
    original=BrokenNote('original')
    with pytest.raises(BrokenNote) as caught:
        with page(Raw()).document:raise original
    assert caught.value is original


def test_open_rejects_mode_two_before_native(tmp_path):
    path=tmp_path/'fixture.xdw';path.write_bytes(b'fixture')
    api=XdwApi.from_raw(NoNative(),multibyte_codepage=932)
    with pytest.raises(ValueError):api.open_document(path,auth=AuthMode.CONDITIONAL_DIALOG)


@pytest.mark.parametrize('start,end,expected', [(0.004,0.008,(0,0)),(0.005,0.01,(1,1)),(-0.005,0.0,(-1,1))])
def test_line_rounds_origin_and_vector_independently(start,end,expected):
    class InspectPage(Page):
        def _add(self,kind,position,data):
            from docuworks_ctypes.geometry import position_to_xdw
            assert (position_to_xdw(position.x),data.nHorVec)==expected
            class Style:
                def _apply_style(self,**kwargs):pass
            return Style()
    p=page();InspectPage(p.document,1).add_line(PointMM(start,1),PointMM(end,1))


@pytest.mark.parametrize('value', [-2147483648,2147483647])
def test_custom_signed_boundaries_preserved(value):
    class Raw:
        def XDW_SetAnnotationCustomAttribute(self,doc,handle,name,kind,storage,reserved):
            assert ctypes.cast(storage,ctypes.POINTER(ctypes.c_int32)).contents.value==value
            return 0
    set_custom_attribute(Raw(),1,2,'name',CustomAttributeKind.INT,value)
