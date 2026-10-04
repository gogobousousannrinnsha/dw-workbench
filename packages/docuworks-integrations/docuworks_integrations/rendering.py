"""One read-only DocuWorks handle for a recognition run."""
import ctypes
from ._storage import note


class XdwRenderer:
    def __init__(self, source_copy, dll_path=None):
        self.source_copy = source_copy
        self.dll_path = dll_path

    def __enter__(self):
        from docuworks_ctypes import XdwApi
        self.api = XdwApi.load(dll_path=self.dll_path)
        self.doc = self.api.open_document(self.source_copy)
        try:
            self.page_count = self.doc.page_count
            self.runtime_version = self.api.runtime_info.version_text
            self.dll_path = str(self.api.runtime_info.dll_path)
        except BaseException as exc:
            self.__exit__(type(exc), exc, exc.__traceback__)
            raise
        return self

    def __exit__(self, exc_type, exc, traceback):
        try:
            self.doc.close()
        except Exception as close_error:
            if exc is None: raise
            exc._ocr_cleanup_failed = True
            note(exc, 'Document close also failed: ' + str(close_error))
        return False

    def render(self, page, folder, dpi):
        from docuworks_ctypes._raw import types as T, constants as C
        from docuworks_ctypes.encoding import wchar_buffer
        from docuworks_ctypes.errors import check_result
        from PIL import Image
        info = T.XDW_PAGE_INFO()
        info.nSize = ctypes.sizeof(info)
        check_result(self.doc.raw.XDW_GetPageInformation(self.doc.handle, page, ctypes.byref(info)), 'XDW_GetPageInformation')
        bmp, png = folder/'image.bmp', folder/'image.png'
        if len(str(bmp).encode('utf-16-le'))//2 > 255:
            raise ValueError('SDK image path exceeds 255 UTF-16 code units')
        options = T.XDW_IMAGE_OPTION()
        options.nSize = ctypes.sizeof(options)
        options.nDpi, options.nColor = dpi, C.XDW_IMAGE_COLOR
        check_result(self.doc.raw.XDW_ConvertPageToImageFileW(self.doc.handle, page, wchar_buffer(str(bmp)), ctypes.byref(options)), 'XDW_ConvertPageToImageFileW')
        with Image.open(bmp) as image:
            width, height = image.size
            image.convert('RGB').save(png)
        bmp.unlink()
        return dict(page_width_mm=info.nWidth/100, page_height_mm=info.nHeight/100,
                    image_width_px=width, image_height_px=height)
