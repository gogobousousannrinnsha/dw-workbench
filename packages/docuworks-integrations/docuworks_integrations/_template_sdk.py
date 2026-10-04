"""Native read-only boundary; Viewer custom properties, not opaque user bytes."""
import ctypes

from .templates import ATTRIBUTE_NAMES


class TemplateSdk:
    def __init__(self, dll_path):
        from docuworks_ctypes import XdwApi
        self.api = XdwApi.load(dll_path)

    def inspect(self, path):
        from docuworks_ctypes import AnnotationType
        from docuworks_ctypes._raw import types as T
        from docuworks_ctypes.errors import check_result
        pages = []
        with self.api.open_document(path) as document:
            for n in range(1, document.page_count + 1):
                info = T.XDW_PAGE_INFO_EX(); info.nSize = ctypes.sizeof(info)
                check_result(document.raw.XDW_GetPageInformation(document.handle, n,
                             ctypes.cast(ctypes.byref(info), ctypes.POINTER(T.XDW_PAGE_INFO))), 'template page info')
                page = dict(page=n, width_mm=info.nWidth/100, height_mm=info.nHeight/100,
                            rotation=info.nDegree, rectangles=[])
                for order, annotation in enumerate(document.page(n).annotations(recursive=False), 1):
                    for child in annotation.descendants():
                        if (child.annotation_type == AnnotationType.RECTANGLE or
                                any(a.name in ATTRIBUTE_NAMES for a in child.custom_attributes())):
                            raise ValueError(f'ページ{n}: グループ・付箋内のテンプレート矩形・属性は未対応です。')
                    attrs = {a.name: dict(kind=a.kind.name, value=a.value) for a in annotation.custom_attributes()
                             if a.name in ATTRIBUTE_NAMES}
                    if annotation.annotation_type != AnnotationType.RECTANGLE:
                        if attrs:
                            raise ValueError(f'ページ{n}: テンプレート属性は四角形へ設定してください。')
                        continue
                    box = annotation._info
                    page['rectangles'].append(dict(annotation_order=order, x=box.nHorPos/100,
                        y=box.nVerPos/100, width=box.nWidth/100, height=box.nHeight/100, attributes=attrs))
                pages.append(page)
        return dict(pages=pages)
