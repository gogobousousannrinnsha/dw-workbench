"""Synthetic SDK and rendering verification, separate from manual Viewer tests."""
import os
import shutil

import pytest

pytestmark = [pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get('DOCUWORKS_REVIEWED_DLL'), reason='set DOCUWORKS_REVIEWED_DLL')]


def test_native_authoring_revision_preview_and_immutability(tmp_path):
    from docuworks_ctypes import XdwApi, OpenMode, RectMM, PointMM, AnnotationType
    from docuworks_integrations import create_review_session, import_reviewed_result, apply_rectangle_template
    from docuworks_integrations import template_authoring as a, reviewed as r
    from reviewed_fixture import create_fixture
    dll = os.environ['DOCUWORKS_REVIEWED_DLL']; api = XdwApi.load(dll)
    original = create_fixture(tmp_path/'fixture', dll, pages=2, blank=True)
    session = create_review_session(original.root, tmp_path/'session', dll_path=dll)
    edited = tmp_path/'edited.xdw'; shutil.copyfile(session.review_xdw, edited)
    with api.open_document(edited, mode=OpenMode.UPDATE) as document:
        document.page(1).add_text(PointMM(15,20), 'AB-123')
        document.page(2).add_text(PointMM(15,20), '80℃')
        document.save()
    reviewed = import_reviewed_result(session.root, edited, tmp_path/'reviewed', dll_path=dll, validation_mode='identity')
    stable = {p:r.sha256(p) for root in (original.root, session.root, reviewed.root) for p in root.rglob('*') if p.is_file()}
    app = tmp_path/'Portable 空白'; app.mkdir()
    draft = a.create_template_draft(app, reviewed.root, name='帳簿A', dll_path=dll)
    with api.open_document(draft.working_xdw, mode=OpenMode.UPDATE) as document:
        for number in (1,2): document.page(number).add_rectangle(RectMM(10,15,100,20))
        document.save()
    draft = a.refresh_template_draft(draft.root, dll_path=dll)
    settings = draft.data['settings']
    for setting, name in zip(settings.values(), ('部品番号', '温度')): setting['name'] = name
    draft = a.update_template_draft(draft.root, settings=settings, expected_revision=draft.revision)
    with api.open_document(draft.working_xdw, mode=OpenMode.UPDATE) as document:
        rect = next(x for x in document.page(1).annotations() if x.annotation_type == AnnotationType.RECTANGLE)
        rect.set_position(PointMM(9,15)); document.save()
    draft = a.refresh_template_draft(draft.root, dll_path=dll)
    assert draft.data['settings'] == settings
    preview = a.preview_template_draft(draft.root)
    assert [f['value'] for f in preview['fields']] == ['AB-123', '80℃']
    image = a.render_template_page(draft.root, 2, dll_path=dll)
    from PIL import Image
    with Image.open(image['path']) as page: assert page.width > 100 and page.height > 100
    template = a.publish_template_draft(draft.root, app, expected_revision=draft.revision, confirm_warnings=True, dll_path=dll)
    result = apply_rectangle_template(template.root, reviewed.root, tmp_path/'structured')
    assert [f['value'] for f in result.data['fields']] == ['AB-123', '80℃']
    v1 = {p:r.sha256(p) for p in template.root.rglob('*') if p.is_file()}
    revised = a.create_template_draft(app, base_template_dir=template.root, dll_path=dll)
    assert revised.data['settings'] == settings
    v2 = a.publish_template_draft(revised.root, app, expected_revision=revised.revision, confirm_warnings=True, dll_path=dll)
    assert v2.root.name == 'v002'
    assert all(r.sha256(p) == digest for p,digest in {**stable, **v1}.items())
    # A legacy 1.0 template has no authoring sample, but can be revised with one.
    from docuworks_integrations import register_rectangle_template
    legacy = register_rectangle_template(template.root/'source-template.xdw', tmp_path/'legacy', name='従来版', dll_path=dll)
    old = a.create_template_draft(app, reviewed.root, base_template_dir=legacy.root, dll_path=dll)
    assert [f['value'] for f in a.preview_template_draft(old.root)['fields']] == ['AB-123', '80℃']
    # Duplicate IDs from copied rectangles must not silently inherit a name.
    from docuworks_integrations._template_authoring_sdk import RECTANGLE_ATTRIBUTE
    first = next(iter(old.data['settings']))
    with api.open_document(old.working_xdw, mode=OpenMode.UPDATE) as document:
        copied = document.page(1).add_rectangle(RectMM(9,15,100,20))
        copied.set_user_attribute(RECTANGLE_ATTRIBUTE, first.encode('ascii'))
        document.save()
    old = a.refresh_template_draft(old.root, dll_path=dll)
    assert first not in old.data['settings']
    assert sum(not s['name'] for s in old.data['settings'].values()) == 2
    with api.open_document(old.working_xdw, mode=OpenMode.UPDATE) as document:
        next(x for x in document.page(1).annotations() if x.annotation_type == AnnotationType.TEXT).set_standard_attribute('%Text', 'CHANGED')
        document.save()
    with pytest.raises(ValueError, match='再取り込み'): a.refresh_template_draft(old.root, dll_path=dll)
