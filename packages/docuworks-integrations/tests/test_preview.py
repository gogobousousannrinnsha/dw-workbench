from pathlib import Path
import pytest

from docuworks_integrations import OcrRegion, PixelRect
from docuworks_integrations._preview import create_preview
from docuworks_integrations.workflow import create_preview as legacy_preview


@pytest.mark.parametrize('empty',[False,True])
def test_preview_preserves_source_geometry_text_and_legacy_entry(tmp_path,empty):
    Image=pytest.importorskip('PIL.Image')
    image=tmp_path/'source.png'
    Image.new('RGB',(300,200),'white').save(image)
    before=image.read_bytes()
    regions=[] if empty else [OcrRegion(' 前|後\n"引用" ',PixelRect(40,70,100,20),confidence=0.75)]
    current=tmp_path/'current'; old=tmp_path/'legacy'
    current.mkdir(); old.mkdir()
    create_preview(image,regions,current)
    legacy_preview(image,regions,old)
    assert image.read_bytes()==before
    assert (current/'preview.png').read_bytes()==(old/'preview.png').read_bytes()
    listing=(current/'regions.md').read_text(encoding='utf-8')
    assert listing==(old/'regions.md').read_text(encoding='utf-8')
    with Image.open(current/'preview.png') as preview:
        assert preview.size==(300,200)
        if empty: assert preview.tobytes()==Image.new('RGB',(300,200),'white').tobytes()
        else: assert preview.getpixel((40,70))==(224,0,32)
    if not empty:
        assert '|1| 前\\|後<br>"引用" |0.750000|' in listing
    else: assert '|1|' not in listing
