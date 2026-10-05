"""SDK persistence of synthetic template properties; not Viewer acceptance."""
import os
import shutil

import pytest

from docuworks_integrations import register_rectangle_template, load_rectangle_template
from docuworks_integrations import reviewed as r
from reviewed_fixture import create_fixture

pytestmark = [pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get('DOCUWORKS_REVIEWED_DLL'), reason='set DOCUWORKS_REVIEWED_DLL')]


@pytest.mark.parametrize('mode', ['valid', 'wrong-type', 'nested', 'tagged-text'])
def test_template_sdk_properties(tmp_path, mode):
    from docuworks_ctypes import XdwApi, OpenMode, RectMM, PointMM, SizeMM, CustomAttributeKind as K
    dll = os.environ['DOCUWORKS_REVIEWED_DLL']
    original = create_fixture(tmp_path/'fixture', dll, pages=1, blank=True)
    source = tmp_path/'帳簿A.xdw'
    shutil.copyfile(original.root/'source/source.xdw', source)
    api = XdwApi.load(dll)
    with api.open_document(source, mode=OpenMode.UPDATE) as document:
        page = document.page(1)
        field = page.add_rectangle(RectMM(10, 20, 80, 20))
        field.set_custom_attribute('用途', K.STRING, '取得')
        field.set_custom_attribute('項目名', K.STRING, '温度')
        field.set_custom_attribute('必須', K.STRING if mode == 'wrong-type' else K.BOOL,
                                   'false' if mode == 'wrong-type' else False)
        field.set_custom_attribute('出力順', K.INT, 2)
        field.set_custom_attribute('結合方法', K.STRING, '空白')
        condition = page.add_rectangle(RectMM(10, 60, 80, 20))
        condition.set_custom_attribute('用途', K.STRING, '適用判定')
        condition.set_custom_attribute('項目名', K.STRING, '帳簿名')
        condition.set_custom_attribute('期待文字', K.STRING, '帳簿A')
        if mode == 'tagged-text': page.add_text(PointMM(100, 100), 'メモ').set_custom_attribute('用途', K.STRING, '取得')
        if mode == 'nested':
            sticky = page.add_sticky(PointMM(100, 100), SizeMM(60, 30), text='メモ')
            list(sticky.descendants())[0].set_custom_attribute('項目名', K.STRING, '不正な入れ子')
        document.save()
    before = r.sha256(source)
    if mode != 'valid':
        with pytest.raises(ValueError): register_rectangle_template(source, tmp_path/'template', dll_path=dll)
        assert not (tmp_path/'template').exists()
    else:
        result = register_rectangle_template(source, tmp_path/'template', dll_path=dll)
        assert load_rectangle_template(result.root) == result
        a, b = result.data['pages'][0]['rectangles']
        assert (a['x'], a['y'], a['width'], a['height']) == (10, 20, 80, 20)
        assert (a['name'], a['required'], a['output_order'], a['join']) == ('温度', False, 2, '空白')
        assert b['expected'] == '帳簿A'
    assert r.sha256(source) == before


@pytest.mark.parametrize('expected', ['帳簿A', '別帳簿'])
def test_native_registration_reviewed_extraction_and_save(tmp_path, expected):
    from docuworks_ctypes import XdwApi, OpenMode, RectMM, PointMM, SizeMM, CustomAttributeKind as K
    from docuworks_integrations import create_review_session, import_reviewed_result, apply_rectangle_template, load_structured_result
    dll = os.environ['DOCUWORKS_REVIEWED_DLL']
    original = create_fixture(tmp_path/'fixture', dll, pages=1, blank=True)
    session = create_review_session(original.root, tmp_path/'session', dll_path=dll)
    edited = tmp_path/'edited.xdw'; shutil.copyfile(session.review_xdw, edited)
    source = tmp_path/'template.xdw'; shutil.copyfile(original.root/'source/source.xdw', source)
    api = XdwApi.load(dll)
    with api.open_document(edited, mode=OpenMode.UPDATE) as document:
        page = document.page(1)
        for x, y, text in [(10,15,'AB-'), (35,15,'123'), (10,35,'80℃'), (10,55,'帳簿A')]:
            page.add_text(PointMM(x,y),text)
        page.add_sticky(PointMM(10,35),SizeMM(60,20),text='作業メモ')
        document.save()
    with api.open_document(source, mode=OpenMode.UPDATE) as document:
        for y, name, purpose in [(10,'部品番号','取得'),(30,'温度','取得'),(50,'帳簿名','適用判定')]:
            rect = document.page(1).add_rectangle(RectMM(5,y,100,20))
            rect.set_custom_attribute('用途',K.STRING,purpose)
            rect.set_custom_attribute('項目名',K.STRING,name)
            if purpose == '適用判定': rect.set_custom_attribute('期待文字',K.STRING,expected)
        document.save()
    template = register_rectangle_template(source,tmp_path/'template',dll_path=dll)
    reviewed = import_reviewed_result(session.root,edited,tmp_path/'reviewed',dll_path=dll,validation_mode='identity')
    stable = {p:r.sha256(p) for root in (original.root,session.root,template.root,reviewed.root) for p in root.rglob('*') if p.is_file()}
    result = apply_rectangle_template(template.root,reviewed.root,tmp_path/'structured')
    assert load_structured_result(result.root) == result
    assert result.data['applicable'] is (expected == '帳簿A')
    assert reviewed.data['excluded_sticky_count'] == 1
    assert result.data['reviewed']['validation']['page_structure_checked'] is False
    if expected == '帳簿A':
        assert [(f['name'],f['value']) for f in result.data['fields']] == [('部品番号','AB-123'),('温度','80℃')]
        assert len(result.data['fields'][0]['sources']) == 2
    else: assert result.data['fields'] == []
    assert all(r.sha256(p) == digest for p,digest in stable.items())
