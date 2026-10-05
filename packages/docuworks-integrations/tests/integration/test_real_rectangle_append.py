"""Opt-in save/reopen and image comparison against the unchanged Core path."""
import hashlib
import os
import shutil
import uuid

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.environ.get('DOCUWORKS_RECTANGLE_NATIVE_TESTS') != '1',
    reason='Set DOCUWORKS_RECTANGLE_NATIVE_TESTS=1 to create disposable native fixtures')]


def inventory(root):
    from docuworks_integrations.results import sha256
    return {p.relative_to(root).as_posix(): sha256(p) for p in root.rglob('*') if p.is_file()}


def snapshot(path):
    from docuworks_ctypes import AnnotationType, XdwApi
    with XdwApi.load().open_document(path) as doc:
        pages = []
        for n in range(1, doc.page_count + 1):
            items = []
            for a in doc.page(n).annotations(recursive=True):
                items.append((int(a.annotation_type), a.position, a.size,
                              a.get_standard_attribute('%Text') if a.annotation_type == AnnotationType.TEXT else None))
            pages.append(items)
        return pages


@pytest.mark.parametrize('existing,filtered', [(False, False), (True, False), (True, True)])
def test_rectangles_match_original_path_with_existing_nested_and_empty_pages(tmp_path, monkeypatch, existing, filtered):
    from PIL import Image
    from reviewed_fixture import create_fixture
    from docuworks_ctypes import XdwApi, OpenMode, PointMM, RectMM, SizeMM, Color
    from docuworks_integrations import _rectangle_sdk
    from docuworks_integrations.derivatives import annotate_rectangles
    from docuworks_integrations.results import OcrDocumentResult, save_ocr_result, sha256
    from docuworks_integrations.rendering import XdwRenderer

    fixture = create_fixture(tmp_path / 'fixture', pages=3)
    if existing:
        source = tmp_path / 'with-existing.xdw'
        shutil.copyfile(fixture.root / fixture.source['path'], source)
        with XdwApi.load().open_document(source, mode=OpenMode.UPDATE) as doc:
            for n in (1, 2, 3):
                page = doc.page(n)
                page.add_text(PointMM(10, 10), '既存文字', fore_color=Color.BLUE)
                page.add_rectangle(RectMM(5, 5, 50, 20), border_color=Color.GREEN)
                page.add_sticky(PointMM(100, 10), SizeMM(40, 30), text='付箋の子文字')
            doc.save()
        assets = {p.relative_to(fixture.root).as_posix(): p for p in fixture.root.rglob('*') if p.is_file()}
        assets[fixture.source['path']] = source
        result = OcrDocumentResult(str(uuid.uuid4()), dict(fixture.source, sha256=sha256(source)),
                                   fixture.ocr, fixture.pages, schema_version='1.1')
        fixture = save_ocr_result(result, tmp_path / 'with-existing-run', assets=assets)
    source = fixture.root / fixture.source['path']
    before = inventory(fixture.root)
    old = snapshot(source)
    settings = dict(min_confidence=.95 if filtered else 0.)
    original, fixed = tmp_path / 'original.xdw', tmp_path / 'fixed.xdw'
    with monkeypatch.context() as m:
        m.setattr(_rectangle_sdk, '_RectangleAppendPage', lambda page, count: page)
        baseline = annotate_rectangles(fixture.root, original, **settings)
    actual = annotate_rectangles(fixture.root, fixed, **settings)
    assert baseline['status'] == actual['status'] == 'VERIFIED'
    assert baseline['regions'] == actual['regions']
    assert actual['annotations_before'] == {str(n): 3 if existing else 0 for n in (1, 2, 3)}
    assert snapshot(original) == snapshot(fixed)
    for old_page, new_page in zip(old, snapshot(fixed)):
        assert new_page[:len(old_page)] == old_page
    assert len(actual['regions']) == (0 if filtered else 6)
    # Compare SDK-rendered pixels, independently of matching attribute getters.
    pixels = []
    for label, path in (('original', original), ('fixed', fixed)):
        hashes = []
        with XdwRenderer(path) as renderer:
            for n in (1, 2, 3):
                folder = tmp_path / f'{label}-page{n}'
                folder.mkdir()
                renderer.render(n, folder, 300)
                with Image.open(folder / 'image.png') as image:
                    hashes.append((image.size, hashlib.sha256(image.tobytes()).hexdigest()))
        pixels.append(hashes)
    assert pixels[0] == pixels[1]
    assert inventory(fixture.root) == before
