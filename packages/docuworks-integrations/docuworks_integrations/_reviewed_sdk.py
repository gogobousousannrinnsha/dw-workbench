"""Native boundary for blank reviews. Imported only when a native operation runs."""
import ctypes
import json
import shutil
from pathlib import Path
from ._performance import measure

from docuworks_ctypes.document import Annotation, Page
from docuworks_ctypes.errors import XdwError
from docuworks_ctypes._raw.constants import XDW_E_INVALIDARG

DOC_ATTRIBUTE = b'DW-OCR.SessionDocument'
PAGE_ATTRIBUTE = b'DW-OCR.SessionPage'
TEXT_ATTRIBUTE = b'DW-OCR.SessionText'


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


class _BlankReviewPage(Page):
    """Append hint for one exclusively owned blank Review page during creation.

    Keep actual SDK annotation information and all inherited value validation.
    A hint mismatch disables the shortcut for this page and uses Core's search.
    Never retain this object across page edits, deletes, or document reopening.
    """

    def __init__(self, page):
        super().__init__(page.document, page.number)
        self._next_index = 1 if self._page_info().nAnnotations == 0 else None

    def _refresh_added_annotation(self, new_handle, *, parent=None):
        if parent is None and self._next_index is not None:
            try:
                info = self._get_annotation_info(None, self._next_index)
            except XdwError as error:
                if error.result != XDW_E_INVALIDARG:
                    raise
            else:
                if info.handle == new_handle.value:
                    self._next_index += 1
                    return Annotation(self, info)
        self._next_index = None
        return super()._refresh_added_annotation(new_handle, parent=parent)


class ReviewSdk:
    def __init__(self, dll_path):
        from docuworks_ctypes import XdwApi
        self.api = XdwApi.load(dll_path)

    @staticmethod
    def attribute(function, *args):
        from docuworks_ctypes._raw.constants import XDW_E_INVALIDARG
        from docuworks_ctypes.errors import check_result
        size = function(*args, None, 0, None)
        if size == XDW_E_INVALIDARG:
            return None
        check_result(size, 'review attribute size')
        if size > 1024 * 1024:
            raise ValueError('review attribute exceeds 1 MiB')
        buffer = (ctypes.c_char * size)()
        actual = function(*args, buffer, size, None)
        check_result(actual, 'review attribute data')
        if actual != size:
            raise RuntimeError('review attribute changed while reading')
        return bytes(buffer)

    @staticmethod
    def _sticky_subtrees(annotation):
        """Count excluded stickies, rejecting text nested outside their ownership."""
        from docuworks_ctypes import AnnotationType
        pending = [(annotation, True, False)]
        count = 0
        while pending:
            current, direct, in_sticky = pending.pop()
            if current.annotation_type == AnnotationType.STICKY:
                count += 1
                in_sticky = True
            if current.annotation_type == AnnotationType.TEXT and not direct and not in_sticky:
                raise ValueError('nested text outside a sticky annotation is unsupported')
            pending.extend((child, False, in_sticky) for child in
                           current.page._children(current.handle, current._info.nChildAnnotations))
        return count

    def inspect(self, path, *, exclude_sticky=False):
        from docuworks_ctypes import AnnotationType
        from docuworks_ctypes._raw import types as T
        from docuworks_ctypes.errors import check_result
        result = {'pages': []}
        if exclude_sticky:
            result['excluded_sticky_count'] = 0
        with self.api.open_document(path) as doc:
            result['identity'] = self.attribute(doc.raw.XDW_GetUserAttribute, doc.handle, DOC_ATTRIBUTE)
            for n in range(1, doc.page_count + 1):
                info = T.XDW_PAGE_INFO_EX()
                info.nSize = ctypes.sizeof(info)
                check_result(doc.raw.XDW_GetPageInformation(doc.handle, n,
                             ctypes.cast(ctypes.byref(info), ctypes.POINTER(T.XDW_PAGE_INFO))), 'review page info')
                page = doc.page(n)
                record = dict(page=n, width_mm=info.nWidth / 100, height_mm=info.nHeight / 100,
                              rotation=info.nDegree, identity=self.attribute(doc.raw.XDW_GetPageUserAttribute,
                              doc.handle, n, PAGE_ATTRIBUTE), items=[])
                for annotation in page.annotations(recursive=False):
                    if exclude_sticky:
                        result['excluded_sticky_count'] += self._sticky_subtrees(annotation)
                    else:
                        for child in annotation.descendants():
                            if child.annotation_type == AnnotationType.TEXT:
                                raise ValueError(f'page {n}: nested text in a group/sticky annotation is unsupported')
                    if annotation.annotation_type != AnnotationType.TEXT:
                        continue
                    a = annotation._info
                    record['items'].append(dict(
                        text=annotation.get_standard_attribute('%Text'), x=a.nHorPos / 100,
                        y=a.nVerPos / 100, width=a.nWidth / 100, height=a.nHeight / 100,
                        rotation=annotation.get_standard_attribute_raw('%TextOrientation'),
                        direction=annotation.get_standard_attribute_raw('%TextDirection'),
                        font_name=annotation.get_standard_attribute('%FontName'),
                        font_size=annotation.get_standard_attribute('%FontSize'),
                        fore_color=annotation.get_standard_attribute_raw('%ForeColor'),
                        word_wrap=annotation.get_standard_attribute('%WordWrap'),
                        identity=self.attribute(doc.raw.XDW_GetAnnotationUserAttribute,
                                                annotation.handle, TEXT_ATTRIBUTE)))
                result['pages'].append(record)
        return result

    def set_origins(self, path, updates):
        """Modify only explicit direct-text attributes on an exclusively owned copy."""
        from docuworks_ctypes import AnnotationType, OpenMode
        with self.api.open_document(path, mode=OpenMode.UPDATE) as doc:
            for update in updates:
                items = [a for a in doc.page(update['page']).annotations(recursive=False)
                         if a.annotation_type == AnnotationType.TEXT]
                items[update['order'] - 1].set_user_attribute(TEXT_ATTRIBUTE.decode('ascii'), update['raw'])
            doc.save()

    def source_pages(self, path):
        with self.api.open_document(path) as doc:
            return [(p._page_info().nWidth / 100, p._page_info().nHeight / 100)
                    for p in (doc.page(n) for n in range(1, doc.page_count + 1))]

    def _blank(self, white, part, p):
        from docuworks_ctypes._raw import types as T, constants as C
        from docuworks_ctypes.encoding import wchar_buffer
        from docuworks_ctypes.errors import check_result
        with measure('review.blank', page=p['page']):
            options = T.XDW_CREATE_OPTION()
            options.nSize = ctypes.sizeof(options)
            options.nFitImage = C.XDW_CREATE_USERDEF
            options.nWidth = round(p['width_mm'] * 100)
            options.nHeight = round(p['height_mm'] * 100)
            options.nZoom = 100
            check_result(self.api.raw.XDW_CreateXdwFromImageFileW(wchar_buffer(str(white)),
                         wchar_buffer(str(part)), ctypes.byref(options)), 'create blank review page')

    @staticmethod
    def _document_identity(doc, common):
        from docuworks_ctypes.errors import check_result
        value = encoded(common)
        check_result(doc.raw.XDW_SetUserAttribute(doc.handle, DOC_ATTRIBUTE, value, len(value), None), 'set review document identity')

    @staticmethod
    def _populate(doc, local_page, p, common):
        from docuworks_ctypes import PointMM, Color
        from docuworks_ctypes.errors import check_result
        with measure('review.text', page=p['page'], item_count=len(p['items'])):
            value = encoded(dict(common, page_id=p['page_id']))
            check_result(doc.raw.XDW_SetPageUserAttribute(doc.handle, local_page, PAGE_ATTRIBUTE,
                             value, len(value), None), 'set review page identity')
            page = _BlankReviewPage(doc.page(local_page)) if p['items'] else None
            for source in p['items']:
                a = page.add_text(PointMM(source['x'], source['y']), source['text'],
                                                   font_size=12, fore_color=Color.RED, back_color=Color.NONE)
                a.set_standard_attribute_raw('%TextDirection', 0)
                a.set_standard_attribute_raw('%TextOrientation', 0)
                a.set_standard_attribute('%WordWrap', False)
                a.set_user_attribute(TEXT_ATTRIBUTE.decode('ascii'), encoded(dict(common,
                                         annotation_id=source['annotation_id'], region_id=source['region_id'])))

    @staticmethod
    def _merge(doc, parts):
        from docuworks_ctypes.encoding import wchar_buffer
        from docuworks_ctypes.errors import check_result
        with measure('review.merge'):
            for n, part in enumerate(parts[1:], 2):
                with measure('review.insert', page=n):
                    check_result(doc.raw.XDW_InsertDocumentW(doc.handle, n, wchar_buffer(str(part)), None), 'insert review page')

    def create(self, identity, identity_hash, output):
        """A: preserve the baseline's blank-join, annotate-all, save-once order."""
        return self._create(identity, identity_hash, output, page_join=False)

    def create_page_join(self, identity, identity_hash, output):
        """B: save and close annotated single pages before joining them."""
        return self._create(identity, identity_hash, output, page_join=True)

    def _create(self, identity, identity_hash, output, *, page_join):
        from PIL import Image
        from docuworks_ctypes import OpenMode
        import sys
        output = Path(output)
        if output.exists():
            raise FileExistsError(output)
        white = output.parent / 'white.bmp'
        Image.new('1', (100, 100), 1).save(white, dpi=(100, 100))
        parts = []
        common = dict(review_id=identity['review_id'], identity_sha256=identity_hash)
        count = len(identity['pages'])
        for p in identity['pages']:
            part = output.parent / f"blank-{p['page']}.xdw"
            self._blank(white, part, p)
            if page_join:
                with measure('review.single_page', page=p['page']):
                    with self.api.open_document(part, mode=OpenMode.UPDATE) as doc:
                        self._document_identity(doc, common)
                        self._populate(doc, 1, p, common)
                        with measure('review.save', page=p['page']):
                            doc.save()
                print(f"Review page saved: {p['page']}/{count}", file=sys.stderr, flush=True)
            parts.append(part)
        with measure('review.copy_first'):
            shutil.copyfile(parts[0], output)
        with self.api.open_document(output, mode=OpenMode.UPDATE) as doc:
            print(f'Review merge: {count} pages', file=sys.stderr, flush=True)
            self._merge(doc, parts)
            self._document_identity(doc, common)
            if not page_join:
                for p in identity['pages']:
                    self._populate(doc, p['page'], p, common)
                    print(f"Review text placed: {p['page']}/{count}", file=sys.stderr, flush=True)
            print('Review final save', file=sys.stderr, flush=True)
            with measure('review.save_final'):
                doc.save()
        # Temporary inputs belong to this session's existing owned staging directory.
        for part in parts:
            part.unlink()
        white.unlink()
        import platform
        return dict(python=platform.python_version(), platform=platform.platform(),
                    api_version=self.api.runtime_info.version_text,
                    dll_sha256=self.api.runtime_info.dll_sha256)
