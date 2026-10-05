"""Create local-only A4 / empty A4 / landscape A3 fixtures using the installed SDK.

Uses the SDK sample's XDW_CREATE_FIT image-size option and the declared W APIs.
Generated images and documents must stay outside the publication set.
"""
import argparse
import ctypes
import os
from pathlib import Path
import shutil


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--dll-path',required=True)
    args=parser.parse_args()
    root=args.output_dir.resolve()
    root.mkdir(parents=True,exist_ok=False)
    from PIL import Image,ImageDraw,ImageFont
    from docuworks_ctypes import XdwApi
    from docuworks_ctypes.enums import OpenMode
    from docuworks_ctypes._raw import types as T, constants as C
    from docuworks_ctypes.encoding import wchar_buffer
    from docuworks_ctypes.errors import check_result
    api=XdwApi.load(dll_path=args.dll_path)
    font=ImageFont.truetype(str(Path(os.environ['WINDIR'])/'Fonts/arial.ttf'),100)
    for n,(width,text) in enumerate(((2100,'PAGE ONE'),(2100,''),(4200,'PAGE THREE')),1):
        image=Image.new('RGB',(width,2970),'white')
        if text: ImageDraw.Draw(image).text((300,300),text,font=font,fill='black')
        bmp=root/f'page{n}.bmp'
        image.save(bmp,dpi=(254,254))
        option=T.XDW_CREATE_OPTION()
        option.nSize=ctypes.sizeof(option)
        option.nFitImage=C.XDW_CREATE_FIT
        check_result(api.raw.XDW_CreateXdwFromImageFileW(wchar_buffer(str(bmp)),
            wchar_buffer(str(root/f'page{n}.xdw')),ctypes.byref(option)),'XDW_CreateXdwFromImageFileW')
    target=root/'multipage.xdw'
    shutil.copyfile(root/'page3.xdw',target)
    with api.open_document(target,mode=OpenMode.UPDATE) as doc:
        for n in (2,1):
            check_result(doc.raw.XDW_InsertDocumentW(doc.handle,1,wchar_buffer(str(root/f'page{n}.xdw')),None),'XDW_InsertDocumentW')
        doc.save()
    with api.open_document(target) as doc:
        assert doc.page_count==3
        for n,expected_width in ((1,21000),(2,21000),(3,42000)):
            info=T.XDW_PAGE_INFO(); info.nSize=ctypes.sizeof(info)
            check_result(doc.raw.XDW_GetPageInformation(doc.handle,n,ctypes.byref(info)),'XDW_GetPageInformation')
            assert abs(info.nWidth-expected_width)<=2 and abs(info.nHeight-29700)<=2
    print(target)


if __name__=='__main__': main()
