"""Native helper scoped to append-only edits of an owned rectangle output copy."""
from docuworks_ctypes.document import Annotation, Page
from docuworks_ctypes.errors import XdwError
from docuworks_ctypes._raw.constants import XDW_E_INVALIDARG


class _RectangleAppendPage(Page):
    """Reuse the direct count already captured by annotate_rectangles.

    Only that consumer may use this object, while adding top-level rectangles
    through this same instance. Never reuse it after other edits or reopening.
    Keep Core's search and real SDK information; only omit repeated page reads.
    An inconsistent count disables reuse for the remainder of this page.
    """

    def __init__(self, page, annotation_count):
        super().__init__(page.document, page.number)
        self._annotation_count = annotation_count

    def _refresh_added_annotation(self, new_handle, *, parent=None):
        if parent is None and self._annotation_count is not None:
            count = self._annotation_count + 1
            try:
                for index in range(1, count + 1):
                    info = self._get_annotation_info(None, index)
                    if info.handle == new_handle.value:
                        self._annotation_count = count
                        return Annotation(self, info)
            except XdwError as error:
                if error.result != XDW_E_INVALIDARG:
                    raise
        self._annotation_count = None
        return super()._refresh_added_annotation(new_handle, parent=parent)
