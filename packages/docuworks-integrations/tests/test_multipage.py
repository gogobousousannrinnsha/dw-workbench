import json
from dataclasses import replace
import pytest
from docuworks_integrations import OcrRegion, PixelRect
from docuworks_integrations.results import load_ocr_result, save_ocr_result, get_region, export_jsonl, sha256
from docuworks_integrations.page_selection import parse_pages, resolve_pages
from docuworks_integrations.recognition import ocr_xdw_pages, ocr_xdw
import docuworks_integrations.recognition as recognition
import docuworks_integrations._preview as preview_module


@pytest.mark.parametrize('text',['','0','-1','3-1','1,,2','x','1-','100001'])
def test_invalid_selection_text(text):
    with pytest.raises(ValueError): parse_pages(text)


def test_selection_order():
    assert parse_pages('5, 1,3-5')==(1,3,4,5)
    assert resolve_pages([3,1,3],3)==(1,3)
    for bad in ([],[0],[True],[4],'1,2'):
        with pytest.raises(ValueError): resolve_pages(bad,3)


class Renderer:
    instances=0
    rendered=[]
    def __init__(self,copy,dll):
        Renderer.instances+=1
        self.copy=copy
        self.page_count=3
        self.dll_path=None
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def render(self,page,folder,dpi):
        Renderer.rendered.append(page)
        (folder/'image.png').write_bytes(b'image'+str(page).encode())
        return dict(page_width_mm=210 if page<3 else 420,page_height_mm=297,
                    image_width_px=1000,image_height_px=1000)


class Engine:
    def __init__(self, failure=None, empty=False):
        self.calls=[]; self.last_raw=None; self.failure=failure; self.empty=empty
    def recognize(self,image):
        page=int(image.parent.name.split('-')[1]); self.calls.append(page)
        if page==2 and self.failure:
            if self.failure=='interrupt': raise KeyboardInterrupt('cancelled')
            raise RuntimeError('GPU failed')
        self.last_raw={'page':page}
        print('engine log')
        return () if self.empty or page==2 else (OcrRegion('text',PixelRect(10,10,100,20),.9),)


@pytest.fixture
def fake(monkeypatch,tmp_path):
    Renderer.instances=0; Renderer.rendered=[]
    monkeypatch.setattr(recognition,'XdwRenderer',Renderer)
    def preview(image,regions,folder):
        (folder/'preview.png').write_bytes(b'preview')
        (folder/'regions.md').write_text('list',encoding='utf-8')
    monkeypatch.setattr(preview_module,'create_preview',preview)
    source=tmp_path/'source.xdw'; source.write_bytes(b'original')
    return source


def test_all_pages_empty_and_geometry(fake,tmp_path,capsys):
    engine=Engine()
    manifest=ocr_xdw_pages(fake,tmp_path/'run',tmp_path,engine=engine)
    assert manifest['schema_version']=='1.1'
    result=load_ocr_result(tmp_path/'run')
    assert [p.page for p in result.pages]==[1,2,3]
    assert result.pages[1].recognition_status=='NO_TEXT_DETECTED'
    assert not result.pages[1].regions
    assert get_region(result,'p0003-r000001').bbox_mm['width']==42
    assert get_region(result,'p0001-r000001').bbox_mm['width']==21
    assert engine.calls==[1,2,3] and Renderer.instances==1
    assert not capsys.readouterr().out
    export_jsonl(result,tmp_path/'all.jsonl')
    assert [json.loads(s)['page'] for s in (tmp_path/'all.jsonl').read_text().splitlines()]==[1,3]
    with pytest.raises(ValueError): get_region(result,1)
    copied=save_ocr_result(result,tmp_path/'copy')
    assert copied.schema_version=='1.1' and copied.pages==result.pages
    assert not list(tmp_path.glob('.recognition-*'))


def test_noncontiguous_and_all_empty(fake,tmp_path):
    ocr_xdw_pages(fake,tmp_path/'selected',tmp_path,pages=[3,1,3],engine=Engine())
    selected=load_ocr_result(tmp_path/'selected')
    assert [p.page for p in selected.pages]==[1,3]
    ocr_xdw_pages(fake,tmp_path/'blank',tmp_path,engine=Engine(empty=True))
    blank=load_ocr_result(tmp_path/'blank')
    export_jsonl(blank,tmp_path/'empty.jsonl')
    assert (tmp_path/'empty.jsonl').read_bytes()==b''
    with pytest.raises(ValueError): get_region(blank,'p0003-r000001')
    from docuworks_integrations.results import validate_result
    with pytest.raises(ValueError): validate_result(replace(blank,schema_version='1.0'))
    wrong=replace(blank,pages=(replace(blank.pages[0],recognition_status='TEXT_DETECTED'),))
    with pytest.raises(ValueError): validate_result(wrong)


@pytest.mark.parametrize('failure',['gpu','interrupt','render','coordinates','original'])
def test_diagnostics_no_partial_publication(fake,tmp_path,monkeypatch,failure):
    engine=Engine(failure=failure if failure in ('gpu','interrupt') else None)
    if failure=='render':
        original_render=Renderer.render
        def render(self,page,folder,dpi):
            if page==2: raise RuntimeError('SDK error')
            return original_render(self,page,folder,dpi)
        monkeypatch.setattr(Renderer,'render',render)
    elif failure in ('coordinates','original'):
        original_recognize=engine.recognize
        def recognize(path):
            regions=original_recognize(path)
            if len(engine.calls)==2:
                if failure=='original': fake.write_bytes(b'changed')
                else: return (OcrRegion('invalid',PixelRect(999,1,20,20)),)
            return regions
        engine.recognize=recognize
    with pytest.raises((RuntimeError,ValueError,KeyboardInterrupt)):
        ocr_xdw_pages(fake,tmp_path/'failed',tmp_path,engine=engine)
    run=tmp_path/'failed'
    assert not (run/'manifest.json').exists()
    assert not (run/'diagnostics/manifest.json').exists()
    error=json.loads((run/'error.json').read_text())
    diagnostics=(run/error['diagnostics']).resolve()
    assert error['completed_pages']==([1,2,3] if failure=='original' else [1])
    assert (diagnostics/'pages/page-0001/result.json').exists()
    if failure in ('gpu','interrupt'):
        assert not (diagnostics/'pages/page-0002/raw-paddle.json').exists()
    with pytest.raises(ValueError, match='unpublished'): load_ocr_result(diagnostics)
    with pytest.raises(FileNotFoundError): load_ocr_result(run)


def test_validation_before_render_and_single_default(fake,tmp_path):
    engine=Engine()
    with pytest.raises(ValueError): ocr_xdw_pages(fake,tmp_path/'bad',tmp_path,pages=[4],engine=engine)
    assert not engine.calls and not Renderer.rendered
    ocr_xdw(fake,tmp_path/'single',tmp_path,engine=engine)
    assert engine.calls==[1]
    with pytest.raises(FileExistsError): ocr_xdw(fake,tmp_path/'single',tmp_path,engine=engine)


def test_single_model_instance(fake,tmp_path,monkeypatch):
    import docuworks_integrations.paddle as paddle
    instances=[]
    def factory(root):
        engine=Engine(); instances.append(engine); return engine
    monkeypatch.setattr(paddle,'PaddleOcrEngine',factory)
    ocr_xdw_pages(fake,tmp_path/'run',tmp_path)
    assert len(instances)==1 and instances[0].calls==[1,2,3]


@pytest.mark.parametrize('body_error',[False,True])
def test_renderer_close_preserves_primary_error(body_error):
    from types import SimpleNamespace
    from docuworks_integrations.rendering import XdwRenderer
    renderer=XdwRenderer(None)
    def close(): raise RuntimeError('close failed')
    renderer.doc=SimpleNamespace(close=close)
    if body_error:
        error=ValueError('GPU failed')
        assert renderer.__exit__(ValueError,error,None) is False
    else:
        with pytest.raises(RuntimeError): renderer.__exit__(None,None,None)
