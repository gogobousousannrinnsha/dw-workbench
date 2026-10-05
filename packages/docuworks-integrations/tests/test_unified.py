import json
from pathlib import Path
from dataclasses import replace
import sys
import pytest

from docuworks_integrations import derivatives as d
from docuworks_integrations import __version__
from docuworks_integrations.settings import Settings, load_settings
from docuworks_integrations.discovery import collect_documents
from docuworks_integrations.results import sha256, load_ocr_result
from test_multipage import fake, Engine
from docuworks_integrations.recognition import ocr_xdw_pages


def test_public_color_names_keep_core_meanings():
    from docuworks_ctypes import Color
    assert all(value==int(getattr(Color,name.upper())) for name,value in d.COLORS.items())


@pytest.mark.parametrize('values',[dict(dpi=400),dict(recursive=1),dict(padding_mm=-1),
    dict(min_confidence=float('nan')),dict(color='pink'),dict(minimum_mm=2)])
def test_invalid_settings(values):
    with pytest.raises(ValueError): Settings(**values)


def test_strict_ini(tmp_path):
    p=tmp_path/'settings.ini'
    for text in ('[ocr]\nunknown=1','[DEFAULT]\nx=1\n[ocr]', '[ocr]\ndpi=3.5',
                 '[ocr]\nrecursive=maybe','[other]'):
        p.write_text(text)
        with pytest.raises(ValueError): load_settings(p)
    p.write_text('[ocr]\ndpi=600\nrecursive=true\njsonl=yes')
    assert load_settings(p)==Settings(dpi=600,recursive=True,jsonl=True)


def test_discovery_dedup_exclusion(tmp_path):
    root=(tmp_path/'input').resolve(); root.mkdir()
    for folder in (root/'sub',root/'OUTPUT'): folder.mkdir()
    for p in (root/'a.XDW',root/'sub/a.xdw',root/'OUTPUT/skip.xdw'): p.write_bytes(b'x')
    found=collect_documents([root,root/'a.XDW',root/'sub'],recursive=True,excluded=[root/'OUTPUT'])
    assert found==[root/'a.XDW',root/'sub/a.xdw']
    assert collect_documents([root],recursive=False)==[root/'a.XDW']


def test_rectangle_geometry_and_saved_only(fake,tmp_path):
    ocr_xdw_pages(fake,tmp_path/'run',tmp_path,engine=Engine())
    fake.unlink() # consumer uses the verified source in the bundle
    report=d.annotate_rectangles(tmp_path/'run',tmp_path/'out.xdw',dry_run=True)
    assert report['integration_version']==__version__
    assert [i['page'] for i in report['regions']]==[1,3]
    assert report['settings']['border_width_pt']==1
    assert report['regions'][1]['ocr_bbox_mm']['width']==42
    assert not (tmp_path/'out.xdw').exists()
    assert d.fit_interval(0,1,210,.5)==(0.,3.)
    assert d.fit_interval(209,1,210,.5)==(207.,3.)
    with pytest.raises(ValueError): d.fit_interval(0,1,2,.5)
    with pytest.raises(ValueError): d.annotate_rectangles(tmp_path/'run',tmp_path/'run/out.xdw',dry_run=True)
    (tmp_path/'exists.xdw').write_bytes(b'old')
    with pytest.raises(FileExistsError): d.annotate_rectangles(tmp_path/'run',tmp_path/'exists.xdw',dry_run=True)


def test_tamper_stops_consumer(fake,tmp_path):
    ocr_xdw_pages(fake,tmp_path/'run',tmp_path,engine=Engine())
    (tmp_path/'run/source/source.xdw').write_bytes(b'tamper')
    with pytest.raises(RuntimeError): d.annotate_rectangles(tmp_path/'run',tmp_path/'out.xdw',dry_run=True)
    assert not (tmp_path/'out.xdw').exists()


def test_maps_no_ocr_and_immutable(fake,tmp_path,monkeypatch):
    PIL=pytest.importorskip('PIL.Image')
    import docuworks_integrations.recognition as rec
    from test_multipage import Renderer
    original=Renderer.render
    def render(self,page,folder,dpi):
        meta=original(self,page,folder,dpi)
        PIL.new('RGB',(1000,1000),'white').save(folder/'image.png')
        return meta
    monkeypatch.setattr(Renderer,'render',render)
    ocr_xdw_pages(fake,tmp_path/'run',tmp_path,engine=Engine())
    before={p.relative_to(tmp_path/'run'):sha256(p) for p in (tmp_path/'run').rglob('*') if p.is_file()}
    monkeypatch.setattr(rec,'ocr_xdw_pages',lambda *a,**k:pytest.fail('consumer reran OCR'))
    try: font=d.resolve_font()
    except FileNotFoundError: pytest.skip('Japanese font unavailable on this host')
    report=d.render_text_maps(tmp_path/'run',tmp_path/'maps',font=font)
    assert report['integration_version']==__version__
    assert len(report['pages'])==3 and report['pages'][1]['region_ids']==[]
    for image in (tmp_path/'maps').rglob('*.png'):
        with PIL.open(image) as im: assert im.size==(1000,1000)
    assert before=={p.relative_to(tmp_path/'run'):sha256(p) for p in (tmp_path/'run').rglob('*') if p.is_file()}
    with pytest.raises(FileExistsError): d.render_text_maps(tmp_path/'run',tmp_path/'maps',font=font)
    with pytest.raises(FileNotFoundError): d.render_text_maps(tmp_path/'run',tmp_path/'bad',font=tmp_path/'missing.ttf')
    assert not (tmp_path/'bad').exists()


def test_workflow_shared_engine_and_failures(fake,tmp_path,monkeypatch):
    from docuworks_integrations import jobs
    from docuworks_ctypes import XdwError
    import docuworks_integrations.recognition as rec
    monkeypatch.setattr(jobs,'resolve_font',lambda *a:None)
    monkeypatch.setattr(jobs,'render_text_maps',lambda *a,**k:None)
    monkeypatch.setattr(jobs,'annotate_rectangles',lambda *a,**k:None)
    root=(tmp_path/'input').resolve(); root.mkdir()
    (root/'a.xdw').write_bytes(b'a'); (root/'b.xdw').write_bytes(b'b')
    engine=Engine()
    job=jobs.process_documents([root,root/'a.xdw'],tmp_path/'out',tmp_path/'runs',tmp_path,
                                engine=engine,settings=Settings(jsonl=True))
    assert job['exit_code']==0 and len(job['documents'])==2
    assert job['integration_version']==__version__
    assert json.loads((tmp_path/'out/job.json').read_text(encoding='utf-8'))['integration_version']==__version__
    assert engine.calls==[1,2,3,1,2,3]
    assert all(r['jsonl']=='SUCCEEDED' for r in job['documents'])
    assert not Path(job['documents'][0]['run_dir']).is_absolute()
    job=jobs.process_documents([root],tmp_path/'failed',tmp_path/'failruns',tmp_path,engine=Engine(failure=True))
    assert job['status']=='FAILED' and job['counts']['ocr']['PENDING']==1
    assert job['counts']['text_maps']['PENDING']==2
    job=jobs.process_documents([root],tmp_path/'interrupt',tmp_path/'intruns',tmp_path,engine=Engine(failure='interrupt'))
    assert job['exit_code']==130


def test_no_input(tmp_path):
    from docuworks_integrations.jobs import process_documents
    root=tmp_path/'empty'; root.mkdir()
    job=process_documents([root],tmp_path/'out',tmp_path/'runs',tmp_path)
    assert job['status']=='NO_INPUT' and job['exit_code']==0
    assert job['integration_version']==__version__


def test_publication_permission_failure_precedes_ocr(fake,tmp_path,monkeypatch):
    from docuworks_integrations import jobs
    monkeypatch.setattr(jobs,'resolve_font',lambda *a:None)
    original=Path.rename
    def denied(self,target):
        if self.name.startswith('.write-probe'): raise PermissionError('host refused rename')
        return original(self,target)
    monkeypatch.setattr(Path,'rename',denied)
    engine=Engine()
    result=jobs.process_documents([fake],tmp_path/'out',tmp_path/'runs',tmp_path,engine=engine)
    assert result['status']=='FAILED' and not engine.calls
    assert result['documents'][0]['ocr']=='PENDING'
    assert 'no OCR was started' in result['error']['message']


def test_new_help(capsys):
    from docuworks_integrations.cli import main
    for command in ('annotate-rectangles','render-text-maps','process-documents'):
        with pytest.raises(SystemExit) as exc: main([command,'--help'])
        assert exc.value.code==0


def test_native_model_path_scope_and_restore(tmp_path, monkeypatch):
    import os
    from types import SimpleNamespace
    from docuworks_integrations.model_loading import local_model_paths
    from docuworks_integrations import model_loading
    if os.name!='nt': pytest.skip('Windows native filename encoding')
    # Exercise a representable code page independently of the runner's locale.
    monkeypatch.setattr(model_loading, '_encode_native_path', lambda p: str(p).encode('utf-8'))
    root=tmp_path/'日本語 models'
    calls=[]
    original=lambda *a,**k:calls.append(a)
    module=SimpleNamespace(Config=original)
    with pytest.raises(RuntimeError):
        with local_model_paths(module,root):
            module.Config(str(root/'PP-OCRv6_medium_det/inference.json'),str(root/'PP-OCRv6_medium_det/inference.pdiparams'))
            assert calls[-1] == tuple(str((root / 'PP-OCRv6_medium_det' / name).resolve()).encode('utf-8')
                                     for name in ('inference.json', 'inference.pdiparams'))
            module.Config('unrelated','params')
            assert calls[-1]==('unrelated','params')
            raise RuntimeError('restore on initialization failure')
    assert module.Config is original


def test_native_model_path_unrepresentable_restores(tmp_path, monkeypatch):
    import os
    from types import SimpleNamespace
    from docuworks_integrations import model_loading
    if os.name != 'nt': pytest.skip('Windows native filename encoding')
    monkeypatch.setattr(model_loading, '_encode_native_path', lambda p: str(p).encode('ascii'))
    root = tmp_path / '日本語 models'
    calls = []
    original = lambda *a: calls.append(a)
    module = SimpleNamespace(Config=original)
    with pytest.raises(ValueError, match='Windows code page') as exc:
        with model_loading.local_model_paths(module, root):
            module.Config(str(root / 'PP-OCRv6_medium_rec/inference.json'),
                          str(root / 'PP-OCRv6_medium_rec/inference.pdiparams'))
    assert isinstance(exc.value.__cause__, UnicodeEncodeError)
    assert calls == []
    assert module.Config is original


def test_native_path_encoder_matches_active_code_page():
    import os
    from docuworks_integrations.model_loading import _encode_native_path
    if os.name != 'nt': pytest.skip('Windows native filename encoding')
    for value in ('ASCII models', '日本語 models', '\U0001f600 models'):
        try:
            expected = value.encode('mbcs')
        except UnicodeEncodeError:
            with pytest.raises(UnicodeEncodeError):
                _encode_native_path(value)
        else:
            assert _encode_native_path(value) == expected


def test_rectangle_failure_keeps_maps_and_integrity_stops(fake,tmp_path,monkeypatch):
    from docuworks_integrations import jobs
    from docuworks_ctypes.errors import XdwError
    from docuworks_ctypes._raw import constants as C
    monkeypatch.setattr(jobs,'resolve_font',lambda *a:None)
    maps=[]
    monkeypatch.setattr(jobs,'render_text_maps',lambda *a,**k:maps.append(a))
    def bad_rectangle(*a,**k): raise XdwError(C.XDW_E_BAD_FORMAT,'save')
    monkeypatch.setattr(jobs,'annotate_rectangles',bad_rectangle)
    result=jobs.process_documents([fake],tmp_path/'out',tmp_path/'runs',tmp_path,engine=Engine())
    assert result['status']=='PARTIAL_FAILED' and len(maps)==1
    assert result['documents'][0]['ocr']=='SUCCEEDED'
    assert result['documents'][0]['rectangles']=='FAILED'
    assert result['documents'][0]['text_maps']=='SUCCEEDED'
    def tamper(*a): raise PermissionError('reparse path replaced')
    monkeypatch.setattr(jobs,'check_source',tamper)
    result=jobs.process_documents([fake],tmp_path/'changed',tmp_path/'changedruns',tmp_path,engine=Engine())
    assert result['status']=='FAILED' and result['error']['type']=='IntegrityError'
