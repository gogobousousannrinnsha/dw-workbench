"""Generate real Japanese XDW files and explicitly synthetic Canonical fixtures."""
import ctypes
from pathlib import Path
import shutil
import uuid


def create_fixture(output, dll_path=None, *, pages=3, blank=False):
    from PIL import Image, ImageDraw, ImageFont
    import os
    from docuworks_ctypes import XdwApi, OpenMode
    from docuworks_ctypes._raw import types as T, constants as C
    from docuworks_ctypes.encoding import wchar_buffer
    from docuworks_ctypes.errors import check_result
    from docuworks_integrations.results import CanonicalOcrRegion, OcrPageResult, OcrDocumentResult, save_ocr_result, sha256
    root=Path(output).resolve();root.mkdir(parents=True,exist_ok=False)
    api=XdwApi.load(dll_path)
    font=ImageFont.truetype(str(Path(os.environ['WINDIR'])/'Fonts/msgothic.ttc'),48)
    items=[];assets={};parts=[]
    for n in range(1,pages+1):
        w,h=(420,297) if n==3 else (210,297)
        image=Image.new('RGB',(w*10,h*10),'white')
        regions=[]
        if not blank and n!=2:
            for i,text in enumerate(('部品番号','部品番号','削除対象'),1):
                x,y,bw,bh=200,i*450,500,80
                ImageDraw.Draw(image).text((x,y),text,font=font,fill='black')
                pts=((x,y),(x+bw,y),(x+bw,y+bh),(x,y+bh))
                regions.append(CanonicalOcrRegion(f'p{n:04d}-r{i:06d}',text,.9,pts,
                    dict(x=x,y=y,width=bw,height=bh),tuple((a/10,b/10) for a,b in pts),
                    dict(x=x/10,y=y/10,width=bw/10,height=bh/10)))
        bmp=root/f'page-{n}.bmp';png=root/f'page-{n}.png'
        image.save(bmp,dpi=(254,254));image.save(png)
        part=root/f'page-{n}.xdw';parts.append(part)
        option=T.XDW_CREATE_OPTION();option.nSize=ctypes.sizeof(option);option.nFitImage=C.XDW_CREATE_USERDEF
        option.nWidth=w*100;option.nHeight=h*100;option.nZoom=100
        check_result(api.raw.XDW_CreateXdwFromImageFileW(wchar_buffer(str(bmp)),wchar_buffer(str(part)),ctypes.byref(option)),'fixture image XDW')
        prefix=f'pages/page-{n:04d}/'
        listing=root/f'page-{n}.md';listing.write_text('Synthetic Canonical fixture; no OCR was executed.\n',encoding='utf-8')
        items.append(OcrPageResult(n,w,h,w*10,h*10,300,prefix+'image.png',None,prefix+'preview.png',prefix+'regions.md',
                                  tuple(regions),recognition_status='TEXT_DETECTED' if regions else 'NO_TEXT_DETECTED'))
        assets.update({prefix+'image.png':png,prefix+'preview.png':png,prefix+'regions.md':listing})
    source=root/'source.xdw';shutil.copyfile(parts[0],source)
    with api.open_document(source,mode=OpenMode.UPDATE) as doc:
        for n,part in enumerate(parts[1:],2):check_result(doc.raw.XDW_InsertDocumentW(doc.handle,n,wchar_buffer(str(part)),None),'fixture insert')
        doc.save()
    assets['source/source.xdw']=source
    result=OcrDocumentResult(str(uuid.uuid4()),dict(type='xdw',path='source/source.xdw',original_path=str(source),
        sha256=sha256(source),page_count=pages),dict(engine='synthetic-fixture',ocr_executed=False),tuple(items),schema_version='1.1')
    return save_ocr_result(result,root/'run',assets=assets)
