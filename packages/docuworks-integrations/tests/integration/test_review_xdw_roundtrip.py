"""Opt-in SDK roundtrip. Never opens the source OCR bundle for update."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil

import pytest

from docuworks_integrations import (
    create_review_xdw, read_review_edit, load_ocr_result, save_corrections,
    apply_corrections, export_effective_jsonl,
)
from docuworks_integrations.results import sha256

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    not os.environ.get('DOCUWORKS_REVIEW_RUN'), reason='set DOCUWORKS_REVIEW_RUN for real SDK tests')]


def hashes(root):
    return {p.relative_to(root).as_posix():sha256(p) for p in root.rglob('*') if p.is_file()}


@pytest.fixture
def review_case(tmp_path):
    from docuworks_ctypes import XdwApi
    source = load_ocr_result(os.environ['DOCUWORKS_REVIEW_RUN'])
    region_id = os.environ.get('DOCUWORKS_REVIEW_REGION', 'p0003-r000001')
    dll = os.environ.get('DOCUWORKS_REVIEW_DLL')
    before = hashes(source.root)
    review_dir = create_review_xdw(source.root, region_id, tmp_path / 'review', dll_path=dll)
    baseline = hashes(review_dir)
    edited = tmp_path / 'edited.xdw'
    shutil.copyfile(review_dir / 'review.xdw', edited)
    api = XdwApi.load(dll)
    yield source, region_id, dll, review_dir, edited, api
    assert hashes(source.root) == before
    assert hashes(review_dir) == baseline


def target(document):
    from docuworks_integrations.review_xdw import _SdkBackend
    values = [a for a in document.page(1).annotations() if _SdkBackend._attribute(a) is not None]
    assert len(values) == 1
    return values[0]


def test_sdk_edit_save_reopen_jsonl(review_case, tmp_path):
    from docuworks_ctypes import OpenMode, PointMM
    source, region_id, dll, folder, edited, api = review_case
    with api.open_document(edited, mode=OpenMode.UPDATE) as doc:
        annotation = target(doc)
        assert annotation.get_standard_attribute('%FontSize') == 12
        assert int(annotation.get_standard_attribute('%ForeColor')) == 255
        annotation.set_standard_attribute('%Text', '訂正済み REVIEW 123')
        annotation.set_position(PointMM(10,10))
        doc.save()
    candidate = read_review_edit(source.root, folder, edited, dll_path=dll)
    assert candidate.correction.region_id == region_id
    saved = save_corrections(source.root, [candidate.correction], tmp_path / 'corrections.json')
    effective = apply_corrections(source.root, saved)
    output = export_effective_jsonl(effective, tmp_path / 'effective.jsonl')
    rows = [json.loads(line) for line in output.read_text(encoding='utf-8').splitlines()]
    changed = next(r for r in rows if r['id'] == region_id)
    assert changed['page'] == 3 and changed['text'] == '訂正済み REVIEW 123'
    assert changed['correction_set_sha256'] == saved.correction_set_sha256
    for old_page, new_page in zip(source.pages,effective.pages):
        for old, new in zip(old_page.regions,new_page.regions):
            data=asdict(new); data.pop('original_text'); data.pop('is_corrected'); data['text']=old.text
            assert data == asdict(old)


def test_sdk_unchanged(review_case, tmp_path):
    source, _, dll, folder, edited, _ = review_case
    candidate=read_review_edit(source.root, folder, edited, dll_path=dll)
    assert candidate.correction is None
    assert save_corrections(source.root, [], tmp_path / 'empty.json').edits == ()


@pytest.mark.parametrize('change', ['blank','delete','missing','duplicate','plain-copy','other-type','extra-page','bad-identity'])
def test_sdk_rejects_invalid_edits(review_case, tmp_path, change):
    from docuworks_ctypes import OpenMode, PointMM, RectMM
    from docuworks_ctypes.encoding import wchar_buffer
    from docuworks_ctypes.errors import check_result
    from docuworks_integrations.review_xdw import ATTRIBUTE
    source, _, dll, folder, edited, api = review_case
    with api.open_document(edited,mode=OpenMode.UPDATE) as doc:
        annotation=target(doc)
        identity=annotation.get_user_attribute(ATTRIBUTE)
        if change=='blank': annotation.set_standard_attribute('%Text','   ')
        elif change=='delete': annotation.remove()
        elif change=='missing': annotation.delete_user_attribute(ATTRIBUTE)
        elif change=='bad-identity': annotation.set_user_attribute(ATTRIBUTE,b'{broken')
        elif change=='other-type':
            annotation.remove()
            doc.page(1).add_rectangle(RectMM(10,10,20,10)).set_user_attribute(ATTRIBUTE,identity)
        elif change=='extra-page':
            check_result(api.raw.XDW_InsertDocumentW(doc.handle,2,wchar_buffer(str(folder/'review.xdw')),None),'insert page')
        else:
            copy=doc.page(1).add_text(PointMM(10,10),'copy')
            if change=='duplicate': copy.set_user_attribute(ATTRIBUTE,identity)
        doc.save()
    if change=='blank':
        candidate=read_review_edit(source.root,folder,edited,dll_path=dll)
        with pytest.raises(ValueError,match='nonblank'):
            save_corrections(source.root,[candidate.correction],tmp_path/'bad.json')
    else:
        with pytest.raises(ValueError): read_review_edit(source.root,folder,edited,dll_path=dll)


def test_sdk_other_review_set(review_case, tmp_path):
    source, region_id, dll, folder, edited, _ = review_case
    other=create_review_xdw(source.root,region_id,tmp_path/'other',dll_path=dll)
    with pytest.raises(ValueError): read_review_edit(source.root,other,edited,dll_path=dll)


@pytest.mark.parametrize('reserved', [False, True])
def test_sdk_original_annotations_preserved_or_collision_rejected(review_case, tmp_path, reserved):
    from dataclasses import replace
    import uuid
    from docuworks_ctypes import OpenMode, PointMM
    from docuworks_integrations import save_ocr_result
    from docuworks_integrations.review_xdw import ATTRIBUTE
    source, region_id, dll, _, _, api = review_case
    seed=tmp_path/'seed.xdw'
    shutil.copyfile(source.root/source.source['path'],seed)
    with api.open_document(seed,mode=OpenMode.UPDATE) as doc:
        a=doc.page(3).add_text(PointMM(20,20),'BACKGROUND')
        a.set_user_attribute(ATTRIBUTE if reserved else 'Other.App.Data',b'keep')
        doc.save()
    paths={source.source['path']}
    for page in source.pages:
        paths.update((page.image,page.preview,page.listing))
        if page.raw: paths.add(page.raw)
    assets={name:source.root/name for name in paths}
    assets[source.source['path']]=seed
    replica=replace(source,run_id=str(uuid.uuid4()),source=dict(source.source,sha256=sha256(seed)),root=None,manifest_sha256=None)
    saved=save_ocr_result(replica,tmp_path/'seed-run',assets=assets)
    before=hashes(saved.root)
    if reserved:
        with pytest.raises(ValueError,match='reserved'):
            create_review_xdw(saved.root,region_id,tmp_path/'seed-review',dll_path=dll)
    else:
        folder=create_review_xdw(saved.root,region_id,tmp_path/'seed-review',dll_path=dll)
        with api.open_document(folder/'review.xdw') as doc:
            annotations=tuple(doc.page(1).annotations())
            assert len(annotations)==2
            background=next(a for a in annotations if a.get_standard_attribute('%Text')=='BACKGROUND')
            assert background.get_user_attribute('Other.App.Data')==b'keep'
        with pytest.raises(ValueError): read_review_edit(source.root,folder,folder/'review.xdw',dll_path=dll)
    assert hashes(saved.root)==before
