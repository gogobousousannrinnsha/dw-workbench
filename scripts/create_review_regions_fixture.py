"""Create a synthetic, local-only SDK document and saved OCR-shaped bundle."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import uuid


def create(output, dll_path):
    from PIL import Image, ImageDraw, ImageFont
    from docuworks_ctypes import XdwApi
    from docuworks_ctypes._raw import types as T, constants as C
    from docuworks_ctypes.encoding import wchar_buffer
    from docuworks_ctypes.errors import check_result
    from docuworks_integrations import CanonicalOcrRegion, OcrPageResult, OcrDocumentResult, save_ocr_result
    from docuworks_integrations.results import sha256
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    image = Image.new('RGB', (2480, 3508), 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(Path(os.environ['WINDIR'])/'Fonts/arial.ttf'), 48)
    texts = ('SAME TEXT', 'SAME TEXT', 'UNSELECTED')
    boxes = [(240, y, 700, 120) for y in (360, 1080, 1800)]
    draw.text((120,100), 'SYNTHETIC SDK TEST / NOT AN OCR MEASUREMENT', font=font, fill='black')
    for i,(text,box) in enumerate(zip(texts,boxes),1):
        draw.text(box[:2],text,font=font,fill='black')
        draw.text((1200,box[1]),'REGION '+str(i),font=font,fill='black')
    image.save(output/'source.bmp',dpi=(300,300))
    image.save(output/'image.png',dpi=(300,300))
    api=XdwApi.load(dll_path=dll_path)
    option=T.XDW_CREATE_OPTION();option.nSize=ctypes.sizeof(option);option.nFitImage=C.XDW_CREATE_FIT
    seed=output/'source.xdw'
    check_result(api.raw.XDW_CreateXdwFromImageFileW(wchar_buffer(str(output/'source.bmp')),
                 wchar_buffer(str(seed)),ctypes.byref(option)), 'create synthetic review source')
    with api.open_document(seed) as doc:
        info=doc.page(1)._page_info()
        width,height=info.nWidth/100,info.nHeight/100
    sx,sy=width/image.width,height/image.height
    regions=[]
    for i,(text,(x,y,w,h)) in enumerate(zip(texts,boxes),1):
        points=((x,y),(x+w,y),(x+w,y+h),(x,y+h))
        regions.append(CanonicalOcrRegion(f'p0001-r{i:06d}',text,.95-i*.05,points,
            dict(x=x,y=y,width=w,height=h),tuple((a*sx,b*sy) for a,b in points),
            dict(x=x*sx,y=y*sy,width=w*sx,height=h*sy)))
    (output/'raw.json').write_text(json.dumps(dict(synthetic=True,ocr_executed=False)),encoding='utf-8')
    (output/'regions.md').write_text('Synthetic fixture. No OCR engine was run.\n',encoding='utf-8')
    prefix='pages/page-0001/'
    page=OcrPageResult(1,width,height,image.width,image.height,300,prefix+'image.png',
                       prefix+'raw.json',prefix+'preview.png',prefix+'regions.md',tuple(regions),
                       recognition_status='TEXT_DETECTED')
    result=OcrDocumentResult(str(uuid.uuid4()),dict(type='xdw',path='source/source.xdw',
        original_path=str(seed),sha256=sha256(seed),page_count=1),
        dict(engine='synthetic-fixture',ocr_executed=False),(page,),schema_version='1.1')
    assets={'source/source.xdw':seed,prefix+'image.png':output/'image.png',prefix+'preview.png':output/'image.png',
            prefix+'raw.json':output/'raw.json',prefix+'regions.md':output/'regions.md'}
    return save_ocr_result(result,output/'run',assets=assets).root


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--dll-path',required=True)
    args=parser.parse_args()
    print(create(args.output,args.dll_path))
