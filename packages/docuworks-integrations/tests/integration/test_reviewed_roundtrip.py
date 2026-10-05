"""Opt-in SDK tests. Every changed document is a disposable generated copy."""
import ctypes
import json
import os
from pathlib import Path
import shutil

import pytest
from docuworks_integrations import create_review_session,import_reviewed_result,load_reviewed_result
from docuworks_integrations._reviewed_sdk import TEXT_ATTRIBUTE,DOC_ATTRIBUTE,PAGE_ATTRIBUTE,ReviewSdk
from docuworks_integrations.results import sha256
from reviewed_fixture import create_fixture

pytestmark=[pytest.mark.integration,pytest.mark.skipif(not os.environ.get('DOCUWORKS_REVIEWED_DLL'),reason='set DOCUWORKS_REVIEWED_DLL')]


@pytest.fixture(scope='module')
def native_base(tmp_path_factory):
    # mkdir inherits the workspace ACL; avoid tmp_path_factory's special 0700 ACL.
    import uuid
    root=Path(os.environ['DOCUWORKS_INTEGRATIONS_TEST_TMP'])/('native-base-'+uuid.uuid4().hex)
    original=create_fixture(root,os.environ['DOCUWORKS_REVIEWED_DLL'])
    return create_review_session(original.root,root/'session',dll_path=os.environ['DOCUWORKS_REVIEWED_DLL'])


@pytest.mark.parametrize('mode',['unchanged','edit','move','add','delete','all-delete','copy','missing','bad','foreign','empty','rotate','vertical','size','rectangle','group','sticky','page-add','page-delete','page-swap','page-rotate','doc-id','page-id'])
def test_sdk_changes(native_base,tmp_path,mode):
    from docuworks_ctypes import XdwApi,OpenMode,PointMM,SizeMM,RectMM
    from docuworks_ctypes._raw import types as T
    from docuworks_ctypes.encoding import wchar_buffer
    from docuworks_ctypes.errors import check_result
    dll=os.environ['DOCUWORKS_REVIEWED_DLL'];api=XdwApi.load(dll)
    before=sha256(native_base.root/'initial.xdw')
    edited=tmp_path/'edited.xdw';shutil.copyfile(native_base.review_xdw,edited)
    with api.open_document(edited,mode=OpenMode.UPDATE) as d:
        a=list(d.page(1).annotations(recursive=False));first=a[0]
        if mode=='edit':first.set_standard_attribute('%Text',' 日本語\n𠮷😀 ')
        if mode=='move':first.set_position(PointMM(33.33,44.44))
        if mode=='add':d.page(2).add_text(PointMM(10,10),'追加黒文字')
        if mode=='delete':a[-1].remove()
        if mode=='all-delete':
            for n in range(1,d.page_count+1):
                for x in reversed(list(d.page(n).annotations(recursive=False))):x.remove()
        if mode=='copy':d.page(1).add_text(PointMM(100,100),'コピー').set_user_attribute(TEXT_ATTRIBUTE.decode(),first.get_user_attribute(TEXT_ATTRIBUTE.decode()))
        if mode=='missing':first.delete_user_attribute(TEXT_ATTRIBUTE.decode())
        if mode=='bad':first.set_user_attribute(TEXT_ATTRIBUTE.decode(),b'{bad')
        if mode=='foreign':
            ident=json.loads(first.get_user_attribute(TEXT_ATTRIBUTE.decode()));ident['review_id']='00000000-0000-0000-0000-000000000000'
            first.set_user_attribute(TEXT_ATTRIBUTE.decode(),json.dumps(ident).encode())
        if mode=='empty':first.set_standard_attribute('%Text','')
        if mode=='rotate':first.set_standard_attribute_raw('%TextOrientation',30)
        if mode=='vertical':first.set_standard_attribute_raw('%TextDirection',1)
        if mode=='size':
            first.set_standard_attribute('%WordWrap',True);first.set_standard_attribute('%AutoResizeHeight',False);first.set_size(SizeMM(60,20))
        if mode=='rectangle':d.page(1).add_rectangle(RectMM(100,100,20,20))
        if mode=='group':
            idx=(ctypes.c_int32*2)(1,2);handle=T.XDW_ANNOTATION_HANDLE()
            check_result(d.raw.XDW_GroupAnnotations(d.handle,1,None,idx,2,ctypes.byref(handle),None),'group')
        if mode=='sticky':d.page(1).add_sticky(PointMM(100,100),SizeMM(60,30),text='nested')
        if mode=='page-add':check_result(d.raw.XDW_InsertDocumentW(d.handle,4,wchar_buffer(str(native_base.root/'initial.xdw')),None),'insert')
        if mode=='page-delete':check_result(d.raw.XDW_DeletePage(d.handle,2,None),'delete page')
        if mode=='page-swap':
            extracted=tmp_path/'first-page.xdw'
            check_result(d.raw.XDW_GetPageW(d.handle,1,wchar_buffer(str(extracted)),None),'extract page')
            check_result(d.raw.XDW_DeletePage(d.handle,1,None),'remove first page')
            check_result(d.raw.XDW_InsertDocumentW(d.handle,2,wchar_buffer(str(extracted)),None),'insert as second page')
        if mode=='page-rotate':check_result(d.raw.XDW_RotatePage(d.handle,1,180,None),'rotate page')
        if mode=='doc-id':check_result(d.raw.XDW_SetUserAttribute(d.handle,DOC_ATTRIBUTE,None,0,None),'delete doc id')
        if mode=='page-id':check_result(d.raw.XDW_SetPageUserAttribute(d.handle,2,PAGE_ATTRIBUTE,None,0,None),'delete page id')
        d.save()
    after=sha256(edited)
    if mode in ('group','sticky','page-add','page-delete','page-swap','page-rotate','doc-id','page-id'):
        with pytest.raises(ValueError):import_reviewed_result(native_base.root,edited,tmp_path/'result',dll_path=dll)
        assert not (tmp_path/'result').exists()
    else:
        actual=ReviewSdk(dll).inspect(edited)
        r=import_reviewed_result(native_base.root,edited,tmp_path/'result',dll_path=dll)
        assert r==load_reviewed_result(r.root)
        for page,raw in zip(r.pages,actual['pages']):
            assert len(page['items'])==len(raw['items'])
            for item,expected in zip(page['items'],raw['items']):
                assert all(item[k]==expected[k] for k in ('text','x','y','width','height','rotation','direction'))
        origins=[i['origin']['status'] for p in r.pages for i in p['items']]
        if mode=='copy':assert origins.count('duplicate')==2
        if mode=='missing':assert 'missing' in origins
        if mode=='bad':assert 'invalid' in origins
        if mode=='foreign':assert 'foreign' in origins
        if mode=='all-delete':assert origins==[] and len(r.pages)==3
    assert sha256(edited)==after and sha256(native_base.root/'initial.xdw')==before


def test_generated_text_has_no_fill_after_reopen(native_base):
    from docuworks_ctypes import XdwApi, Color
    api = XdwApi.load(os.environ['DOCUWORKS_REVIEWED_DLL'])
    for path in (native_base.root / 'initial.xdw', native_base.review_xdw):
        with api.open_document(path) as document:
            annotations = [a for n in range(1, document.page_count + 1)
                           for a in document.page(n).annotations(recursive=False)]
            assert annotations
            assert all(a.get_standard_attribute_raw('%BackColor') == int(Color.NONE)
                       for a in annotations)
