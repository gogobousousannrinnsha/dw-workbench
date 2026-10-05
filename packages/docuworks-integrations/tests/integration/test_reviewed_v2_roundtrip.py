"""Real SDK acceptance on disposable synthetic documents; never Viewer evidence."""
import ctypes
import json
import os
from pathlib import Path
import shutil
import uuid

import pytest

from docuworks_integrations import (create_review_session, import_reviewed_result, load_reviewed_result,
                                    set_review_origins, get_reviewed_origins)
from docuworks_integrations import reviewed as m
from docuworks_integrations import _reviewed_v2 as v2
from docuworks_integrations._reviewed_sdk import ReviewSdk, TEXT_ATTRIBUTE, DOC_ATTRIBUTE
from reviewed_fixture import create_fixture

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not os.environ.get('DOCUWORKS_REVIEWED_DLL'), reason='set DOCUWORKS_REVIEWED_DLL')]


@pytest.fixture(scope='module')
def native_v2():
    root = Path(os.environ['DOCUWORKS_INTEGRATIONS_TEST_TMP']) / ('v2-native-' + uuid.uuid4().hex)
    original = create_fixture(root, os.environ['DOCUWORKS_REVIEWED_DLL'])
    session = create_review_session(original.root, root/'session', dll_path=os.environ['DOCUWORKS_REVIEWED_DLL'])
    return original, session


@pytest.mark.parametrize('mode', ['multi', 'sticky', 'overlap', 'group', 'partial', 'foreign', 'empty',
                                  'all-delete', 'geometry', 'page-extra', 'page-remove', 'page-rotate', 'doc-id'])
def test_native_identity_snapshot(native_v2, tmp_path, mode):
    from docuworks_ctypes import XdwApi, OpenMode, PointMM, SizeMM
    from docuworks_ctypes._raw import types as T
    from docuworks_ctypes.encoding import wchar_buffer
    from docuworks_ctypes.errors import check_result
    original, session = native_v2
    stable = {p: m.sha256(p) for root in (original.root, session.root) for p in root.rglob('*') if p.is_file()}
    dll = os.environ['DOCUWORKS_REVIEWED_DLL']
    api = XdwApi.load(dll)
    edited = tmp_path/'edited.xdw'
    shutil.copyfile(session.review_xdw, edited)
    with api.open_document(edited, mode=OpenMode.UPDATE) as document:
        items = list(document.page(1).annotations(recursive=False))
        first = items[0]
        if mode in ('sticky', 'overlap'):
            document.page(1).add_sticky(PointMM(100,100), SizeMM(60,30), text='作業メモ：温度80℃')
        if mode == 'overlap': document.page(1).add_text(PointMM(100,100), '本文として残す')
        if mode == 'group':
            indices = (ctypes.c_int32*2)(1,2); handle = T.XDW_ANNOTATION_HANDLE()
            check_result(document.raw.XDW_GroupAnnotations(document.handle,1,None,indices,2,ctypes.byref(handle),None), 'group')
        if mode in ('partial','foreign'):
            refs = [v2.reference(session.identity, i['region_id']) for i in session.identity['pages'][0]['items'][:2]]
            refs[1]['region_id'] = 'unknown'
            payload = dict(schema=v2.ORIGIN_SCHEMA,schema_version='2.0',review_id=session.review_id,
                           identity_sha256=m._digest(session._identity_bytes),origins=refs)
            if mode == 'foreign': payload['review_id'] = str(uuid.uuid4())
            first.set_user_attribute(TEXT_ATTRIBUTE.decode(), m._bytes(payload))
        if mode == 'empty': first.set_standard_attribute('%Text', '')
        if mode == 'geometry':
            first.set_standard_attribute('%Text',' ８０ ℃\n𠮷😀 ')
            first.set_position(PointMM(33.33,44.44))
            first.set_standard_attribute_raw('%TextOrientation',30)
            first.set_standard_attribute_raw('%TextDirection',1)
        if mode == 'all-delete':
            for n in range(1,document.page_count+1):
                for item in reversed(list(document.page(n).annotations(recursive=False))): item.remove()
        if mode == 'page-extra':
            check_result(document.raw.XDW_InsertDocumentW(document.handle,4,wchar_buffer(str(session.root/'initial.xdw')),None),'extra page')
        if mode == 'page-remove': check_result(document.raw.XDW_DeletePage(document.handle,2,None),'remove page')
        if mode == 'page-rotate': check_result(document.raw.XDW_RotatePage(document.handle,1,180,None),'rotate page')
        if mode == 'doc-id': check_result(document.raw.XDW_SetUserAttribute(document.handle,DOC_ATTRIBUTE,None,0,None),'remove identity')
        document.save()
    if mode == 'multi':
        ids = [i['region_id'] for i in session.identity['pages'][0]['items'][:2]]
        edited = set_review_origins(session.root, edited, tmp_path/'assigned.xdw',
                                   [dict(page=1,order=1,region_ids=ids),dict(page=1,order=2,region_ids=[])],
                                   expected_source_sha256=m.sha256(edited),dll_path=dll)
    input_hash = m.sha256(edited)
    if mode in ('group','doc-id'):
        with pytest.raises(ValueError):
            import_reviewed_result(session.root,edited,tmp_path/'result',dll_path=dll,validation_mode='identity')
        assert not (tmp_path/'result').exists()
    else:
        expected = ReviewSdk(dll).inspect(edited,exclude_sticky=True)
        result = import_reviewed_result(session.root,edited,tmp_path/'result',dll_path=dll,validation_mode='identity')
        assert load_reviewed_result(result.root) == result
        assert len(result.pages) == len(expected['pages'])
        for page, raw in zip(result.pages, expected['pages']):
            assert all(page[key] == raw[key] for key in ('page','width_mm','height_mm','rotation'))
            assert len(page['items']) == len(raw['items'])
            for actual, item in zip(page['items'],raw['items']):
                assert all(actual[key] == item[key] for key in ('text','x','y','width','height','rotation','direction'))
        flat = [i for p in result.pages for i in p['items']]
        if mode == 'multi':
            assert get_reviewed_origins(flat[0]) == tuple(ids)
            assert flat[1]['origins'] == [] and flat[1]['origin_evidence']['status'] == 'none'
        if mode in ('sticky','overlap'):
            assert result.data['excluded_sticky_count'] == 1
            assert not any('作業メモ' in i['text'] for i in flat)
            # The saved XDW bytes still contain all sticky content; only extraction excludes it.
            assert m.sha256(result.root/'source-review.xdw') == input_hash
        if mode == 'overlap': assert any(i['text'] == '本文として残す' for i in flat)
        if mode == 'partial': assert flat[0]['origin_evidence']['status'] == 'partial' and len(flat[0]['origins']) == 1
        if mode == 'foreign': assert flat[0]['origin_evidence']['status'] == 'foreign' and flat[0]['origins'] == []
        if mode == 'empty': assert flat[0]['text'] == '' and 'EMPTY_TEXT' in flat[0]['diagnostics']
        if mode == 'all-delete': assert flat == [] and len(result.pages) == 3
        if mode.startswith('page-'):
            assert result.data['validation']['page_structure_checked'] is False
            with pytest.raises(ValueError): import_reviewed_result(session.root,edited,tmp_path/'strict',dll_path=dll)
    assert m.sha256(edited) == input_hash
    assert all(m.sha256(path) == digest for path,digest in stable.items())
