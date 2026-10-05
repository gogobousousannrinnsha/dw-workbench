import json
import subprocess
import sys
from dataclasses import replace, asdict
from pathlib import Path
from types import SimpleNamespace
import uuid
import pytest
from docuworks_integrations.results import (CanonicalOcrRegion,OcrPageResult,OcrDocumentResult,
    save_ocr_result,load_ocr_result,get_region,export_jsonl,sha256,validate_result)


def fixture_result(tmp_path, two=False):
    asset=tmp_path/'asset'
    asset.write_bytes(b'unchanged')
    pages=[]
    assets={'source/source.xdw':asset}
    for page in range(1,3 if two else 2):
        # Different physical dimensions ensure per-page transforms are used.
        s=page/10
        p=f'pages/page-{page:04d}/'
        region=CanonicalOcrRegion(f'p{page:04d}-r000001',' テスト ',.9,
            ((10,10),(30,10),(30,20),(10,20)),dict(x=10,y=10,width=20,height=10),
            ((10*s,10*s),(30*s,10*s),(30*s,20*s),(10*s,20*s)),dict(x=10*s,y=10*s,width=20*s,height=10*s))
        pages.append(OcrPageResult(page,100*s,100*s,100,100,300,p+'image.png',p+'raw-paddle.json',p+'preview.png',p+'regions.md',(region,)))
        for name in ('image.png','raw-paddle.json','preview.png','regions.md'): assets[p+name]=asset
    result=OcrDocumentResult(str(uuid.uuid4()),dict(type='xdw',path='source/source.xdw',
        original_path=str(tmp_path/'missing-original.xdw'),sha256=sha256(asset),page_count=len(pages)),{},tuple(pages))
    return result,assets


def test_roundtrip_and_jsonl_without_external_original(tmp_path):
    result,assets=fixture_result(tmp_path,True)
    saved=save_ocr_result(result,tmp_path/'run',assets=assets)
    assert saved.pages==result.pages
    assert get_region(saved,'p0002-r000001').bbox_mm['width']==4
    with pytest.raises(ValueError): get_region(saved,1)
    exported=export_jsonl(saved,tmp_path/'regions.jsonl')
    rows=[json.loads(s) for s in exported.read_text(encoding='utf-8').splitlines()]
    assert len(rows)==2 and rows[0]['text']==' テスト '
    assert rows[0]['run_id']==saved.run_id and rows[1]['page']==2
    assert rows[0]['manifest_sha256']==saved.manifest_sha256
    with pytest.raises(FileExistsError): export_jsonl(saved,exported)
    with pytest.raises(ValueError): export_jsonl(saved,saved.root/'derived.jsonl')
    copy=save_ocr_result(saved,tmp_path/'copy')
    assert copy.pages==saved.pages and copy.run_id==saved.run_id
    with pytest.raises(ValueError): save_ocr_result(saved,saved.root/'nested')


@pytest.mark.parametrize('change',['version','duplicate','outside','mm','bbox','zero','crossed','nan','page','missing_hash'])
def test_reject_invalid_contract_even_with_rehashed_json(tmp_path,change):
    result,assets=fixture_result(tmp_path)
    saved=save_ocr_result(result,tmp_path/'run',assets=assets)
    manifest=saved.root/'manifest.json'
    m=json.loads(manifest.read_text())
    page=saved.root/'pages/page-0001/result.json'
    p=json.loads(page.read_text(encoding='utf-8'))
    r=p['regions'][0]
    if change=='version': m['schema_version']='2.0'
    elif change=='duplicate': p['regions'].append(r.copy())
    elif change=='outside': r['polygon_px'][0][0]=-1
    elif change=='mm': r['polygon_mm'][0][0]=99
    elif change=='bbox': r['bbox_px']['width']=21
    elif change=='zero': r['polygon_px']=[[10,10]]*4
    elif change=='crossed': r['polygon_px'][1],r['polygon_px'][2]=r['polygon_px'][2],r['polygon_px'][1]
    elif change=='nan': r['confidence']=float('nan')
    elif change=='page': p['page']=2
    elif change=='missing_hash': del m['files']['pages/page-0001/image.png']
    page.write_text(json.dumps(p),encoding='utf-8')
    m['files']['pages/page-0001/result.json']=sha256(page)
    manifest.write_text(json.dumps(m),encoding='utf-8')
    with pytest.raises((ValueError,TypeError)): load_ocr_result(saved.root)


@pytest.mark.parametrize('change',['image','missing','traversal'])
def test_bundle_integrity(tmp_path,change):
    result,assets=fixture_result(tmp_path)
    saved=save_ocr_result(result,tmp_path/'run',assets=assets)
    image=saved.root/'pages/page-0001/image.png'
    if change=='image': image.write_bytes(b'changed')
    elif change=='missing': image.unlink()
    else:
        m=json.loads((saved.root/'manifest.json').read_text())
        m['files']['../asset']=sha256(tmp_path/'asset')
        (saved.root/'manifest.json').write_text(json.dumps(m))
    with pytest.raises((ValueError,RuntimeError,FileNotFoundError)): load_ocr_result(saved.root)
    with pytest.raises((ValueError,RuntimeError,FileNotFoundError)): export_jsonl(saved,tmp_path/'bad.jsonl')
    assert not (tmp_path/'bad.jsonl').exists()


def test_selection_and_existing_output(tmp_path):
    result,assets=fixture_result(tmp_path)
    saved=save_ocr_result(result,tmp_path/'run',assets=assets)
    assert get_region(saved,1)==get_region(saved,'1')==get_region(saved,'p0001-r000001')
    for bad in (True,0,-1,2,'p0002-r000001'):
        with pytest.raises(ValueError): get_region(saved,bad)
    with pytest.raises(FileExistsError): save_ocr_result(result,tmp_path/'run',assets=assets)


def test_consumer_original_override_and_bundle_protection(tmp_path):
    from docuworks_integrations.consumers import mark_region
    from docuworks_integrations.legacy_results import convert_ocr_run
    result,assets=fixture_result(tmp_path)
    saved=save_ocr_result(result,tmp_path/'run',assets=assets)
    with pytest.raises(FileNotFoundError): mark_region(saved.root,1,tmp_path/'marked.xdw',dry_run=True)
    report=mark_region(saved.root,1,tmp_path/'marked.xdw',input_xdw=tmp_path/'asset',dry_run=True)
    assert report['execution']['verified'] and not (tmp_path/'marked.xdw').exists()
    wrong=tmp_path/'wrong.xdw'
    wrong.write_bytes(b'wrong')
    with pytest.raises(RuntimeError): mark_region(saved.root,1,tmp_path/'marked.xdw',input_xdw=wrong,dry_run=True)
    with pytest.raises(ValueError): mark_region(saved.root,1,saved.root/'marked.xdw',input_xdw=tmp_path/'asset',dry_run=True)
    with pytest.raises(ValueError): convert_ocr_run(saved.root,saved.root/'converted')


def test_no_optional_imports_or_core_required(tmp_path):
    result,assets=fixture_result(tmp_path)
    saved=save_ocr_result(result,tmp_path/'run',assets=assets)
    import docuworks_integrations
    package=Path(docuworks_integrations.__file__).resolve().parents[1]
    code='''import sys
sys.path.insert(0,sys.argv[1])
from docuworks_integrations import load_ocr_result, export_jsonl
from docuworks_integrations.cli import main
r=load_ocr_result(sys.argv[2])
export_jsonl(r,sys.argv[3])
assert not any(n.split('.')[0] in ('paddle','paddleocr','paddlex','PIL','cv2','numpy','docuworks_ctypes') for n in sys.modules)
'''
    subprocess.run([sys.executable,'-S','-c',code,str(package),str(saved.root),str(tmp_path/'std.jsonl')],check=True)


def test_copy_failure_does_not_publish(tmp_path):
    result,assets=fixture_result(tmp_path)
    expected={name:'0'*64 for name in assets}
    with pytest.raises(RuntimeError): save_ocr_result(result,tmp_path/'run',assets=assets,expected_hashes=expected)
    assert not (tmp_path/'run').exists() and not list(tmp_path.glob('.ocr-*'))
