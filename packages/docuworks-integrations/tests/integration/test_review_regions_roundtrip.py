"""Opt-in multi-region SDK test, using a synthetic saved run (no OCR required)."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil

import pytest

from docuworks_integrations import (
    load_ocr_result, create_review_xdw_regions, read_review_edits,
    save_corrections, apply_corrections, export_effective_jsonl,
)
from docuworks_integrations.review_xdw import ATTRIBUTE, _SdkBackend
from docuworks_integrations.results import sha256

pytestmark=[pytest.mark.integration,pytest.mark.skipif(not os.environ.get('DOCUWORKS_REVIEW_REGIONS_RUN'),
    reason='set DOCUWORKS_REVIEW_REGIONS_RUN to a synthetic multi-region bundle')]
IDS=('p0001-r000001','p0001-r000002')


def hashes(root):
    return {p.relative_to(root).as_posix():sha256(p) for p in root.rglob('*') if p.is_file()}


def targets(doc):
    result={}
    for a in doc.page(1).annotations(recursive=True):
        identity=_SdkBackend._attribute(a)
        if identity is not None:result[json.loads(identity)['region_id']]=a
    return result


@pytest.fixture
def sdk_case(tmp_path):
    from docuworks_ctypes import XdwApi
    original=load_ocr_result(os.environ['DOCUWORKS_REVIEW_REGIONS_RUN'])
    assert len(original.pages)==1 and len(original.pages[0].regions)==3
    assert original.pages[0].regions[0].text==original.pages[0].regions[1].text
    before=hashes(original.root)
    dll=os.environ.get('DOCUWORKS_REVIEW_DLL')
    folder=create_review_xdw_regions(original.root,tuple(reversed(IDS)),tmp_path/'review',dll_path=dll)
    baseline=hashes(folder)
    edited=tmp_path/'edited.xdw';shutil.copyfile(folder/'review.xdw',edited)
    yield original,folder,edited,XdwApi.load(dll_path=dll),dll
    assert hashes(original.root)==before and hashes(folder)==baseline


@pytest.mark.parametrize('mode',['first','second','both','none','swap'])
def test_sdk_duplicate_text_identity(sdk_case,tmp_path,mode):
    from docuworks_ctypes import OpenMode
    original,folder,edited,api,dll=sdk_case
    expected={}
    with api.open_document(edited,mode=OpenMode.UPDATE) as doc:
        a,b=(targets(doc)[i] for i in IDS)
        assert a.get_standard_attribute('%FontSize')==b.get_standard_attribute('%FontSize')==12
        assert int(a.get_standard_attribute('%ForeColor'))==int(b.get_standard_attribute('%ForeColor'))==255
        if mode in ('first','both','swap'):expected[IDS[0]]=' 日本語\n"訂正 A" '
        if mode in ('second','both'):expected[IDS[1]]='訂正 B'
        for region_id,text in expected.items():targets(doc)[region_id].set_standard_attribute('%Text',text)
        if mode=='swap':
            pa,pb=a.position,b.position
            a.set_position(pb);b.set_position(pa)
        doc.save()
    before=sha256(edited)
    candidate=read_review_edits(original.root,folder,edited,dll_path=dll)
    assert {c.region_id:c.after_text for c in candidate.corrections}==expected
    assert candidate.unchanged_region_ids==tuple(i for i in IDS if i not in expected)
    assert sha256(edited)==before
    saved=save_corrections(original.root,candidate.corrections,tmp_path/'corrections.json')
    effective=apply_corrections(original.root,saved)
    for old,new in zip(original.pages[0].regions,effective.pages[0].regions):
        values=asdict(new);assert values.pop('original_text')==old.text
        assert values.pop('is_corrected')==(old.id in expected)
        assert values.pop('text')==expected.get(old.id,old.text)
        orig=asdict(old);orig.pop('text');assert values==orig
    output=export_effective_jsonl(effective,tmp_path/'effective.jsonl')
    rows=[json.loads(line) for line in output.read_text(encoding='utf-8').splitlines()]
    assert len(rows)==3 and rows[2]['text']==original.pages[0].regions[2].text
    assert all(row['correction_set_sha256']==saved.correction_set_sha256 for row in rows)


@pytest.mark.parametrize('mode',['delete','copy','plain-copy','missing','malformed','duplicate','type','page','blank'])
def test_sdk_reject_partial_or_invalid(sdk_case,tmp_path,mode):
    from docuworks_ctypes import OpenMode,PointMM,RectMM
    from docuworks_ctypes.encoding import wchar_buffer
    from docuworks_ctypes.errors import check_result
    original,folder,edited,api,dll=sdk_case
    with api.open_document(edited,mode=OpenMode.UPDATE) as doc:
        a,b=(targets(doc)[i] for i in IDS)
        a.set_standard_attribute('%Text','valid edit')
        identity=b.get_user_attribute(ATTRIBUTE)
        if mode=='delete':b.remove()
        elif mode in ('copy','plain-copy'):
            copy=doc.page(1).add_text(PointMM(100,100),'copy')
            if mode=='copy':copy.set_user_attribute(ATTRIBUTE,identity)
        elif mode=='missing':b.delete_user_attribute(ATTRIBUTE)
        elif mode=='malformed':b.set_user_attribute(ATTRIBUTE,b'{bad')
        elif mode=='duplicate':b.set_user_attribute(ATTRIBUTE,a.get_user_attribute(ATTRIBUTE))
        elif mode=='type':
            b.remove();doc.page(1).add_rectangle(RectMM(10,10,20,10)).set_user_attribute(ATTRIBUTE,identity)
        elif mode=='page':
            check_result(api.raw.XDW_InsertDocumentW(doc.handle,2,wchar_buffer(str(folder/'review.xdw')),None),'insert page')
        elif mode=='blank':b.set_standard_attribute('%Text',' \u3000 ')
        doc.save()
    if mode=='blank':
        candidate=read_review_edits(original.root,folder,edited,dll_path=dll)
        assert len(candidate.corrections)==2
        with pytest.raises(ValueError,match='nonblank'):
            save_corrections(original.root,candidate.corrections,tmp_path/'bad.json')
        assert not (tmp_path/'bad.json').exists()
    else:
        with pytest.raises(ValueError):read_review_edits(original.root,folder,edited,dll_path=dll)


def test_sdk_other_set(sdk_case,tmp_path):
    original,folder,edited,_,dll=sdk_case
    other=create_review_xdw_regions(original.root,IDS,tmp_path/'other',dll_path=dll)
    with pytest.raises(ValueError):read_review_edits(original.root,other,edited,dll_path=dll)
