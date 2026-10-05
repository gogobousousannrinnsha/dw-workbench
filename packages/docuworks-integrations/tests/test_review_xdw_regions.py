"""Format-2 multi-region review contracts without a native DLL."""
from dataclasses import asdict, replace
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

import pytest

from docuworks_integrations import (
    create_review_xdw, read_review_edit, create_review_xdw_regions, read_review_edits,
    save_ocr_result, save_corrections, apply_corrections, export_effective_jsonl,
)
from docuworks_integrations import review_xdw as module
from test_canonical_results import fixture_result
from test_corrections import tree_hash
from test_review_xdw import FakeSdk, read, write

IDS = ('p0002-r000001', 'p0002-r000002')


def multi_run(tmp_path, version='1.0'):
    result, assets = fixture_result(tmp_path, two=True)
    page = result.pages[1]
    region = page.regions[0]
    regions = tuple(replace(region, id=f'p0002-r{i+1:06d}', text=region.text if i < 2 else 'excluded',
                            polygon_px=tuple((x+25*i,y) for x,y in region.polygon_px),
                            bbox_px=dict(region.bbox_px,x=region.bbox_px['x']+25*i),
                            polygon_mm=tuple((x+5*i,y) for x,y in region.polygon_mm),
                            bbox_mm=dict(region.bbox_mm,x=region.bbox_mm['x']+5*i)) for i in range(3))
    pages = (result.pages[0], replace(page, regions=regions))
    if version == '1.1':
        pages = tuple(replace(p, recognition_status='TEXT_DETECTED') for p in pages)
    return save_ocr_result(replace(result, schema_version=version, pages=pages), tmp_path/'run', assets=assets)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    original = multi_run(tmp_path)
    sdk = FakeSdk(original.pages[1])
    monkeypatch.setattr(module, '_SdkBackend', lambda dll: sdk)
    return original, sdk


def create(setup, tmp_path, ids=IDS):
    original, sdk = setup
    folder = create_review_xdw_regions(original.root, ids, tmp_path/'review')
    edited = tmp_path/'edited.xdw'
    shutil.copyfile(folder/'review.xdw', edited)
    return original, sdk, folder, edited


@pytest.mark.parametrize('version', ['1.0', '1.1'])
@pytest.mark.parametrize('mode', ['first', 'second', 'both', 'none', 'swap-positions'])
def test_identity_and_effective_result(tmp_path, monkeypatch, version, mode):
    original = multi_run(tmp_path, version)
    sdk = FakeSdk(original.pages[1])
    monkeypatch.setattr(module, '_SdkBackend', lambda dll: sdk)
    before = tree_hash(original.root)
    original, _, folder, edited = create((original,sdk),tmp_path,tuple(reversed(IDS)))
    assert [r['region_id'] for r in read(folder/'review.json')['regions']] == list(IDS)
    assert sdk.extracted_page == 2
    data = read(edited)
    a,b = data['annotations']
    assert a['text'] == b['text'] and a['x'] != b['x']
    if mode in ('first','both','swap-positions'): a['text']=' 日本語\n"訂正 A" '
    if mode in ('second','both'): b['text']='訂正 B'
    if mode == 'swap-positions': a['x'],b['x']=b['x'],a['x']
    data['annotations'].reverse()  # Enumeration order must not identify a region.
    write(edited,data)
    candidate=read_review_edits(original.root,folder,edited)
    expected={}
    if mode in ('first','both','swap-positions'):expected[IDS[0]]=a['text']
    if mode in ('second','both'):expected[IDS[1]]=b['text']
    assert {c.region_id:c.after_text for c in candidate.corrections} == expected
    assert candidate.unchanged_region_ids == tuple(i for i in IDS if i not in expected)
    assert tuple(c.region_id for c in candidate.corrections) == tuple(i for i in IDS if i in expected)
    saved=save_corrections(original.root,candidate.corrections,tmp_path/'corrections.json')
    effective=apply_corrections(original.root,saved)
    for old_page,new_page in zip(original.pages,effective.pages):
        for old,new in zip(old_page.regions,new_page.regions):
            values=asdict(new)
            assert values.pop('original_text')==old.text
            assert values.pop('is_corrected')==(old.id in expected)
            assert values.pop('text')==expected.get(old.id,old.text)
            old_values=asdict(old);old_values.pop('text')
            assert values==old_values
    out=export_effective_jsonl(effective,tmp_path/'effective.jsonl')
    rows=[json.loads(line) for line in out.read_text(encoding='utf-8').splitlines()]
    assert sum(row['is_corrected'] for row in rows)==len(expected)
    assert all(row['correction_set_sha256']==saved.correction_set_sha256 for row in rows)
    assert tree_hash(original.root)==before


@pytest.mark.parametrize('ids', [[], (), None, 'p0002-r000001', [1], [IDS[0],IDS[0]],
                               ['p9999-r000001'], [IDS[0],'p0001-r000001']])
def test_invalid_selection(setup,tmp_path,ids):
    original,_=setup
    with pytest.raises(ValueError):create_review_xdw_regions(original.root,ids,tmp_path/'bad')
    assert not (tmp_path/'bad').exists()


def test_one_selected_and_version_separation(setup,tmp_path):
    original,_,folder,edited=create(setup,tmp_path,[IDS[0]])
    assert read_review_edits(original.root,folder,edited).unchanged_region_ids==(IDS[0],)
    with pytest.raises(ValueError):read_review_edit(original.root,folder,edited)
    legacy=create_review_xdw(original.root,IDS[0],tmp_path/'legacy')
    assert read_review_edit(original.root,legacy,legacy/'review.xdw').correction is None
    with pytest.raises(ValueError):read_review_edits(original.root,legacy,legacy/'review.xdw')


@pytest.mark.parametrize('change',['delete','copy','plain-copy','missing','malformed','duplicate','unknown',
                                    'foreign','version','kind','pages','dimensions','unreadable'])
def test_invalid_structure_all_or_nothing(setup,tmp_path,change):
    original,_,folder,edited=create(setup,tmp_path)
    data=read(edited)
    a,b=data['annotations']
    a['text']='valid edit'
    identity=json.loads(b['identity'])
    if change=='delete':data['annotations'].pop()
    elif change=='copy':data['annotations'].append(b.copy())
    elif change=='plain-copy':data['annotations'].append(dict(b,identity=None))
    elif change=='missing':b['identity']=None
    elif change=='malformed':b['identity']='{broken'
    elif change=='duplicate':b['identity']=a['identity']
    elif change=='unknown':identity['region_id']='p0002-r000003'
    elif change=='foreign':identity['review_id']=str(uuid.uuid4())
    elif change=='version':identity['schema_version']='1.0'
    elif change=='kind':b['kind']='other'
    elif change=='pages':data['pages']=2
    elif change=='dimensions':data['width']+=1
    elif change=='unreadable':b['text']=None
    if change in ('unknown','foreign','version'):b['identity']=json.dumps(identity)
    write(edited,data)
    with pytest.raises(ValueError):read_review_edits(original.root,folder,edited)


@pytest.mark.parametrize('blank',['',' ','\u3000\n\t'])
def test_valid_and_blank_edits_reject_entire_save(setup,tmp_path,blank):
    original,_,folder,edited=create(setup,tmp_path)
    data=read(edited);data['annotations'][0]['text']='good';data['annotations'][1]['text']=blank
    write(edited,data)
    candidate=read_review_edits(original.root,folder,edited)
    assert len(candidate.corrections)==2
    with pytest.raises(ValueError,match='nonblank'):
        save_corrections(original.root,candidate.corrections,tmp_path/'bad.json')
    assert not (tmp_path/'bad.json').exists()


@pytest.mark.parametrize('change',['empty','duplicate','order','text','extra','version','count','bool','run','hash'])
def test_manifest_validation(setup,tmp_path,change):
    original,_,folder,edited=create(setup,tmp_path)
    data=read(folder/'review.json')
    if change=='empty':data['regions']=[]
    elif change=='duplicate':data['regions'][1]=data['regions'][0]
    elif change=='order':data['regions'].reverse()
    elif change=='text':data['regions'][1]['original_text']='wrong'
    elif change=='extra':data['regions'][0]['extra']=1
    elif change=='version':data['schema_version']='1.0'
    elif change=='count':data['annotation_count']=1
    elif change=='bool':data['source_page']=True
    elif change=='run':data['run_id']=str(uuid.uuid4())
    elif change=='hash':data['manifest_sha256']='0'*64
    write(folder/'review.json',data)
    with pytest.raises(ValueError):read_review_edits(original.root,folder,edited)


@pytest.mark.parametrize('operation',['save','publish','race','source','lost-identity'])
def test_generation_failure_preserves_outputs(setup,tmp_path,monkeypatch,operation):
    original,sdk=setup
    add=sdk.add_text;publish=module.publish_new
    calls=[]
    def failing_add(path,region,identity):
        add(path,region,identity);calls.append(region.id)
        if len(calls)!=2:return
        if operation=='save':raise OSError('second save failed')
        if operation=='source':(original.root/original.pages[0].image).write_bytes(b'changed')
        if operation=='lost-identity':
            data=read(path);data['annotations'][0]['identity']=None;write(path,data)
    def failing_publish(source,destination):
        if operation=='race':
            destination.mkdir();(destination/'keep').write_text('keep');publish(source,destination)
        raise OSError('publish failed')
    monkeypatch.setattr(sdk,'add_text',failing_add)
    if operation in ('publish','race'):monkeypatch.setattr(module,'publish_new',failing_publish)
    with pytest.raises((OSError,ValueError,RuntimeError)):
        create_review_xdw_regions(original.root,IDS,tmp_path/'bad')
    if operation=='race':assert (tmp_path/'bad/keep').read_text()=='keep'
    else:assert not (tmp_path/'bad').exists()
    assert not list(tmp_path.glob('.review-*'))


@pytest.mark.parametrize('which',['xdw','manifest','source','read-error'])
def test_input_change_or_read_error(setup,tmp_path,monkeypatch,which):
    original,sdk,folder,edited=create(setup,tmp_path)
    inspect=sdk.inspect
    def changed(path):
        result=inspect(path)
        if which=='read-error':raise OSError('native read failed')
        target={'xdw':edited,'manifest':folder/'review.json','source':original.root/original.pages[0].image}[which]
        with target.open('ab') as stream:stream.write(b' ')
        return result
    monkeypatch.setattr(sdk,'inspect',changed)
    with pytest.raises(OSError if which=='read-error' else RuntimeError):
        read_review_edits(original.root,folder,edited)


def test_background_collision_paths_and_relocation(setup,tmp_path):
    original,sdk=setup
    sdk.background=[dict(kind='other',identity=None,text=None,x=1,y=2)]
    original,_,folder,edited=create(setup,tmp_path)
    assert len(read(edited)['annotations'])==3
    before=tree_hash(folder)
    with pytest.raises(FileExistsError):create_review_xdw_regions(original.root,IDS,folder)
    assert tree_hash(folder)==before
    with pytest.raises(ValueError):create_review_xdw_regions(original.root,IDS,original.root/'nested')
    with pytest.raises(ValueError):read_review_edits(original.root,folder,original.root/'source/source.xdw')
    private=tmp_path/('.review-'+uuid.uuid4().hex)
    with pytest.raises(ValueError):create_review_xdw_regions(original.root,IDS,private)
    shutil.copytree(folder,private)
    with pytest.raises(ValueError):read_review_edits(original.root,private,edited)
    sdk.background=read(edited)['annotations']
    with pytest.raises(ValueError,match='reserved'):create_review_xdw_regions(original.root,IDS,tmp_path/'collision')
    moved=tmp_path/'moved';shutil.move(str(original.root),str(moved))
    moved_review=tmp_path/'moved-review';shutil.move(str(folder),str(moved_review))
    assert not read_review_edits(moved,moved_review,edited).corrections


def test_other_review_and_schema(setup,tmp_path):
    import jsonschema
    original,_,folder,edited=create(setup,tmp_path)
    other=create_review_xdw_regions(original.root,IDS,tmp_path/'other')
    with pytest.raises(ValueError):read_review_edits(original.root,other,edited)
    schema=read(Path(module.__file__).with_name('ocr-review-2.0.schema.json'))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(read(folder/'review.json'),schema)
    for a in read(edited)['annotations']:jsonschema.validate(json.loads(a['identity']),schema)


def test_lazy_import():
    code='''
import sys
sys.path.insert(0,sys.argv[1])
class Block:
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'docuworks_ctypes','PIL','paddle','paddleocr','numpy'}:raise AssertionError(fullname)
sys.meta_path.insert(0,Block())
from docuworks_integrations import create_review_xdw_regions,read_review_edits,ReviewEditsCandidate
'''
    subprocess.run([sys.executable,'-I','-S','-c',code,str(Path(module.__file__).parents[1])],check=True)
