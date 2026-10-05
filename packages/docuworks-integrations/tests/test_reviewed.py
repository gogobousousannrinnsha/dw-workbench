"""Independent result contracts. Fake native boundary, real persistence/validation."""
import base64
from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from docuworks_integrations import reviewed as m
from docuworks_integrations import save_ocr_result
from test_canonical_results import fixture_result


def write(path, value): path.write_bytes(m._bytes(value))
def read(path): return json.loads(path.read_text(encoding='utf-8'))
def hashes(root): return {p.relative_to(root).as_posix():m.sha256(p) for p in root.rglob('*') if p.is_file()}


class FakeSdk:
    def __init__(self, pages): self.pages = pages
    def source_pages(self, path): return [(p.page_width_mm,p.page_height_mm) for p in self.pages]
    def create(self, identity, digest, path):
        common = dict(review_id=identity['review_id'], identity_sha256=digest)
        pages=[]
        for p in identity['pages']:
            items=[]
            for i in p['items']:
                items.append(dict(text=i['text'],x=i['x'],y=i['y'],width=12.34,height=7.63,
                    rotation=0,direction=0,font_name='test-font',font_size=12,
                    fore_color=255,word_wrap=False,
                    identity=dict(common,annotation_id=i['annotation_id'],region_id=i['region_id'])))
            pages.append(dict(page=p['page'],width_mm=p['width_mm'],height_mm=p['height_mm'],rotation=0,
                              identity=dict(common,page_id=p['page_id']),items=items))
        write(path,dict(identity=common,pages=pages))
        return {'api_version':'fake','dll_sha256':None}
    def inspect(self,path):
        data=read(path)
        def enc(v): return None if v is None else (v.encode() if isinstance(v,str) else m._bytes(v))
        data['identity']=enc(data['identity'])
        for p in data['pages']:
            p['identity']=enc(p['identity'])
            if p.get('nested'): raise ValueError('nested text unsupported')
            for i in p['items']:i['identity']=enc(i['identity'])
        return data


def setup(tmp_path,monkeypatch,empty=False,version='1.1'):
    result,assets=fixture_result(tmp_path,two=True)
    pages=tuple(replace(p,regions=() if empty or p.page==2 else p.regions,
                       recognition_status='NO_TEXT_DETECTED' if empty or p.page==2 else 'TEXT_DETECTED') for p in result.pages)
    if version=='1.0':pages=result.pages
    run=save_ocr_result(replace(result,pages=pages,schema_version=version),tmp_path/'run',assets=assets)
    sdk=FakeSdk(pages);monkeypatch.setattr(m,'_sdk',lambda dll:sdk)
    session=m.create_review_session(run.root,tmp_path/'session')
    return run,session,sdk


@pytest.mark.parametrize('empty',[False,True])
@pytest.mark.parametrize('version',['1.0','1.1'])
def test_roundtrip_independent_of_canonical_and_mutable_view(tmp_path,monkeypatch,empty,version):
    run,s,_=setup(tmp_path,monkeypatch,empty,version)
    before=hashes(run.root);stable=hashes(s.root)
    result=m.import_reviewed_result(s.root,s.review_xdw,tmp_path/'result')
    assert len(result.pages)==2 and result.data['unit']=='mm'
    assert hashes(run.root)==before and hashes(s.root)==stable
    assert m.load_reviewed_result(result.root)==result
    view=result.data;view['pages'].clear();assert len(result.pages)==2
    view=s.identity;view['pages'].clear();assert len(s.identity['pages'])==2
    shutil.move(run.root,tmp_path/'offline-run')
    again=m.import_reviewed_result(s.root,s.review_xdw,tmp_path/'again')
    assert again.result_id!=result.result_id
    shutil.move(s.root,tmp_path/'offline-session')
    exported=m.export_reviewed_jsonl(result,tmp_path/'export.jsonl')
    assert exported.read_bytes()==(result.root/'reviewed.jsonl').read_bytes()
    assert all('confidence' not in i for p in result.pages for i in p['items'])


@pytest.mark.parametrize('mode',['edit','add','delete','duplicate','missing','bad','foreign','empty','rotate','nested'])
def test_editor_changes_and_origins(tmp_path,monkeypatch,mode):
    _,s,_=setup(tmp_path,monkeypatch)
    d=read(s.review_xdw);items=d['pages'][0]['items'];a=items[0]
    if mode=='edit':a.update(text=' 日本語\n𠮷😀 ',x=7.77,y=8.88,width=42.1,height=3.25)
    if mode=='add':
        a=dict(a,text='新規',identity=None);d['pages'][1]['items'].append(a)
    if mode=='delete':items.clear()
    if mode=='duplicate':items.append(dict(a,text='コピー'))
    if mode=='missing':a['identity']=None
    if mode=='bad':a['identity']='{bad'
    if mode=='foreign':a['identity']['review_id']='00000000-0000-0000-0000-000000000000'
    if mode=='empty':a['text']=' \u3000 '
    if mode=='rotate':a.update(rotation=30,direction=1)
    if mode=='nested':d['pages'][0]['nested']=True
    write(s.review_xdw,d)
    if mode=='nested':
        with pytest.raises(ValueError,match='nested'):m.import_reviewed_result(s.root,s.review_xdw,tmp_path/'result')
        assert not (tmp_path/'result').exists();return
    r=m.import_reviewed_result(s.root,s.review_xdw,tmp_path/'result')
    after=[i for p in r.pages for i in p['items']]
    if mode=='delete':assert after==[]
    else:
        assert after[-1]['text']==a['text'] if mode!='duplicate' else after[-1]['text']=='コピー'
        for key in ('x','y','width','height','rotation','direction'):
            assert after[0][key]==d['pages'][0]['items'][0][key]
    statuses={'duplicate':'duplicate','missing':'missing','bad':'invalid','foreign':'foreign'}
    if mode in statuses:assert all(i['origin']['status']==statuses[mode] for i in after)
    if mode=='add':assert after[-1]['origin']['status']=='missing'
    if mode=='empty':assert after[0]['diagnostics']==['EMPTY_TEXT']


@pytest.mark.parametrize('change',['doc','page-id','page-order','page-count','dimension','page-rotation'])
def test_reject_document_structure(tmp_path,monkeypatch,change):
    _,s,_=setup(tmp_path,monkeypatch)
    d=read(s.review_xdw)
    if change=='doc':d['identity']=None
    if change=='page-id':d['pages'][0]['identity']=None
    if change=='page-order':d['pages'].reverse()
    if change=='page-count':d['pages'].pop()
    if change=='dimension':d['pages'][0]['width_mm']+=1
    if change=='page-rotation':d['pages'][0]['rotation']=180
    write(s.review_xdw,d)
    with pytest.raises(ValueError):m.import_reviewed_result(s.root,s.review_xdw,tmp_path/'result')
    assert not (tmp_path/'result').exists()


@pytest.mark.parametrize('name',['identity.json','session.json','initial.xdw','manifest.json'])
def test_session_corruption(tmp_path,monkeypatch,name):
    _,s,_=setup(tmp_path,monkeypatch)
    with (s.root/name).open('ab') as f:f.write(b'bad')
    with pytest.raises((ValueError,RuntimeError)):m.import_reviewed_result(s.root,s.review_xdw,tmp_path/'result')
    assert not (tmp_path/'result').exists()


@pytest.mark.parametrize('name',sorted(m.RESULT_FILES))
def test_result_corruption(tmp_path,monkeypatch,name):
    _,s,_=setup(tmp_path,monkeypatch)
    r=m.import_reviewed_result(s.root,s.review_xdw,tmp_path/'result')
    with (r.root/name).open('ab') as f:f.write(b'bad')
    with pytest.raises((ValueError,RuntimeError)):m.load_reviewed_result(r.root)


@pytest.mark.parametrize('change',['uuid','order','nan','origin','diagnostics','page','jsonl'])
def test_semantic_validation_even_if_rehashed(tmp_path,monkeypatch,change):
    _,s,_=setup(tmp_path,monkeypatch)
    r=m.import_reviewed_result(s.root,s.review_xdw,tmp_path/'result')
    d=read(r.root/'reviewed.json');a=d['pages'][0]['items'][0]
    if change=='uuid':a['item_id']='bad'
    if change=='order':a['order']=True
    if change=='nan':a['width']=-1
    if change=='origin':a['origin']['status']='missing'
    if change=='diagnostics':a['diagnostics']=['wrong']
    if change=='page':d['pages'][0]['page']=True
    write(r.root/'reviewed.json',d)
    (r.root/'reviewed.jsonl').write_bytes(b'wrong' if change=='jsonl' else m._jsonl(d))
    m._write_manifest(r.root,m.RESULT_SCHEMA,m.RESULT_FILES)
    with pytest.raises(ValueError):m.load_reviewed_result(r.root)


def test_input_race_publication_failure_and_protected_destinations(tmp_path,monkeypatch):
    run,s,sdk=setup(tmp_path,monkeypatch)
    before=hashes(run.root)
    for dest in (run.root/'bad',s.root/'bad',s.root):
        with pytest.raises((ValueError,FileExistsError)):
            m.import_reviewed_result(s.root,s.review_xdw,dest)
    with pytest.raises(ValueError):m.import_reviewed_result(s.root,s.root/'initial.xdw',tmp_path/'bad')
    original=sdk.inspect
    def inspect(path):
        data=original(path)
        with s.review_xdw.open('ab') as f:f.write(b' ')
        return data
    monkeypatch.setattr(sdk,'inspect',inspect)
    with pytest.raises(RuntimeError,match='changed'):m.import_reviewed_result(s.root,s.review_xdw,tmp_path/'race')
    assert not (tmp_path/'race').exists()
    monkeypatch.setattr(sdk,'inspect',original)
    def fail(*args):raise OSError('publication failure')
    monkeypatch.setattr(m,'publish_new',fail)
    with pytest.raises(OSError):m.import_reviewed_result(s.root,s.review_xdw,tmp_path/'fail')
    assert not (tmp_path/'fail').exists() and hashes(run.root)==before


def test_incomplete_document_and_staging_rejected(tmp_path,monkeypatch):
    result,assets=fixture_result(tmp_path,two=True)
    run=save_ocr_result(replace(result,pages=result.pages[:1]),tmp_path/'run',assets=assets)
    with pytest.raises(ValueError,match='complete'):m.create_review_session(run.root,tmp_path/'session')
    with pytest.raises(ValueError,match='staging'):m.load_review_session(tmp_path/'.review-session-abc')


def test_native_not_imported_by_public_import():
    code="import sys; from docuworks_integrations import ReviewSession, ReviewedResult, load_reviewed_result; assert 'docuworks_ctypes' not in sys.modules; assert 'PIL' not in sys.modules"
    subprocess.run([sys.executable,'-B','-c',code],check=True)


@pytest.mark.parametrize('empty',[False,True])
def test_published_json_matches_packaged_schemas(tmp_path,monkeypatch,empty):
    import jsonschema
    _,s,_=setup(tmp_path,monkeypatch,empty)
    r=m.import_reviewed_result(s.root,s.review_xdw,tmp_path/'result')
    checks=[(s.root/'identity.json','review-session-identity'),(s.root/'session.json','review-session'),
            (s.root/'manifest.json','review-session-manifest'),(r.root/'reviewed.json','reviewed-result'),
            (r.root/'manifest.json','reviewed-result-manifest')]
    for path,name in checks:
        schema=read(Path(m.__file__).with_name(name+'-1.0.schema.json'))
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(read(path),schema,format_checker=jsonschema.FormatChecker())
    schema=read(Path(m.__file__).with_name('reviewed-text-1.0.schema.json'))
    for line in (r.root/'reviewed.jsonl').read_text(encoding='utf-8').splitlines():
        jsonschema.validate(json.loads(line),schema)


@pytest.mark.parametrize('change',['color','wrap','position','rotation','direction','text','size','create-failure'])
def test_generation_verifies_saved_text_and_style(tmp_path,monkeypatch,change):
    run,s,sdk=setup(tmp_path,monkeypatch)
    before=hashes(run.root)
    inspect=sdk.inspect
    def changed(path):
        data=inspect(path);i=data['pages'][0]['items'][0]
        if change=='color':i['fore_color']=0
        if change=='wrap':i['word_wrap']=True
        if change=='position':i['x']+=1
        if change=='rotation':i['rotation']=30
        if change=='direction':i['direction']=1
        if change=='text':i['text']='changed'
        if change=='size':i['width']=0
        if change=='create-failure':raise OSError('SDK failure after creating file')
        return data
    monkeypatch.setattr(sdk,'inspect',changed)
    with pytest.raises((ValueError,RuntimeError,OSError)):
        m.create_review_session(run.root,tmp_path/'failed-session')
    assert not (tmp_path/'failed-session').exists() and hashes(run.root)==before
