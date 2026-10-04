"""Native operations on owned copies only; imported by the authoring worker."""
import base64
import hashlib
import json
import uuid

from ._template_sdk import TemplateSdk
from ._reviewed_sdk import ReviewSdk
from .templates import ATTRIBUTE_NAMES

RECTANGLE_ATTRIBUTE = 'DW-OCR.TemplateRectangle'


def fingerprint(snapshot):
    snapshot = dict(snapshot)
    snapshot.pop('excluded_sticky_count', None)
    encoded = json.dumps(snapshot, sort_keys=True, ensure_ascii=False,
                         default=lambda value: base64.b64encode(value).decode('ascii')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


class AuthoringSdk:
    def __init__(self, dll_path=None):
        self.template = TemplateSdk(dll_path)
        self.review = ReviewSdk(dll_path)
        self.api = self.template.api

    def inspect(self, path):
        from docuworks_ctypes import AnnotationType
        from docuworks_ctypes.errors import XdwError
        from docuworks_ctypes._raw.constants import XDW_E_INVALIDARG
        data = self.template.inspect(path)
        data['body_sha256'] = fingerprint(self.review.inspect(path, exclude_sticky=True))
        with self.api.open_document(path) as doc:
            for page in data['pages']:
                annotations = list(doc.page(page['page']).annotations(recursive=False))
                for rect in page['rectangles']:
                    annotation = annotations[rect['annotation_order'] - 1]
                    assert annotation.annotation_type == AnnotationType.RECTANGLE
                    try:
                        raw = annotation.get_user_attribute(RECTANGLE_ATTRIBUTE)
                        value = raw.decode('ascii')
                        rect['uid'] = value if str(uuid.UUID(value)) == value else None
                    except (ValueError, UnicodeError):
                        rect['uid'] = None
                    except XdwError as exc:
                        if exc.result != XDW_E_INVALIDARG:
                            raise
                        rect['uid'] = None
        return data

    @staticmethod
    def _attributes(annotation, setting):
        from docuworks_ctypes import CustomAttributeKind as K
        for attribute in annotation.custom_attributes():
            if attribute.name in ATTRIBUTE_NAMES:
                annotation.delete_custom_attribute(attribute.name)
        values = [('用途', K.STRING, setting['purpose']), ('項目名', K.STRING, setting['name']),
                  ('結合方法', K.STRING, setting['join'])]
        if setting['purpose'] == '適用判定':
            values.append(('期待文字', K.STRING, setting['expected']))
        else:
            values.extend([('必須', K.BOOL, setting['required']), ('出力順', K.INT, setting['order'])])
        for name, kind, value in values:
            annotation.set_custom_attribute(name, kind, value)

    def write(self, path, pages, settings=None):
        from docuworks_ctypes import OpenMode, AnnotationType
        with self.api.open_document(path, mode=OpenMode.UPDATE) as doc:
            for page in pages:
                annotations = list(doc.page(page['page']).annotations(recursive=False))
                for rect in page['rectangles']:
                    annotation = annotations[rect['annotation_order'] - 1]
                    if annotation.annotation_type != AnnotationType.RECTANGLE:
                        raise ValueError('矩形の対応が変更されました。再読込してください。')
                    annotation.set_user_attribute(RECTANGLE_ATTRIBUTE, rect['uid'].encode('ascii'))
                    if settings is not None:
                        self._attributes(annotation, settings[rect['uid']])
            doc.save()

    def seed(self, path, definition):
        """Legacy templates acquire a new sample, retaining their definitions."""
        from docuworks_ctypes import OpenMode, AnnotationType, RectMM
        with self.api.open_document(path, mode=OpenMode.UPDATE) as doc:
            if doc.page_count != len(definition['pages']):
                raise ValueError('見本とテンプレートのページ数が異なります。')
            for page in definition['pages']:
                target = doc.page(page['page'])
                for annotation in reversed(list(target.annotations(recursive=False))):
                    if annotation.annotation_type == AnnotationType.RECTANGLE:
                        annotation.remove()
                for index, rect in enumerate(page['rectangles'], 1):
                    annotation = target.add_rectangle(RectMM(*(rect[k] for k in ('x', 'y', 'width', 'height'))))
                    setting = dict(name=rect['name'], purpose='取得' if rect['purpose'] == 'field' else '適用判定',
                                   expected=rect['expected'] or '', required=rect['required'],
                                   join=rect['join'], order=rect['output_order'] or index)
                    self._attributes(annotation, setting)
            doc.save()

    def render(self, source, page, folder):
        from .rendering import XdwRenderer
        with XdwRenderer(source, dll_path=self.template.api.runtime_info.dll_path) as renderer:
            return renderer.render(page, folder, 150)
