"""Disposable native A/B evidence. Synthetic fixtures are never represented as OCR."""
import argparse
import base64
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import uuid


def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def jsonable(value):
    if isinstance(value, bytes): return {'base64':base64.b64encode(value).decode('ascii')}
    if isinstance(value, dict): return {k:jsonable(v) for k,v in value.items()}
    if isinstance(value, (tuple,list)): return [jsonable(v) for v in value]
    return value


def fixture(root, pages):
    from PIL import Image
    from docuworks_integrations._reviewed_sdk import ReviewSdk, encoded
    from docuworks_integrations.results import CanonicalOcrRegion, OcrPageResult, OcrDocumentResult, save_ocr_result, sha256
    root.mkdir(parents=True, exist_ok=False)
    identity = dict(review_id=str(uuid.uuid4()), pages=[])
    results=[]; assets={}
    png=root/'white.png'; Image.new('RGB',(1000,1414),'white').save(png)
    listing=root/'synthetic.md'; listing.write_text('Synthetic; OCR was not executed.\n',encoding='utf-8')
    for n in range(1,pages+1):
        items=[];regions=[]
        for i in range(20):
            x,y=10+(i//10)*100,10+(i%10)*25
            text=f'頁{n:04d} 項目{i+1:02d}'
            rid=f'p{n:04d}-r{i+1:06d}'
            items.append(dict(annotation_id=str(uuid.uuid4()),region_id=rid,text=text,x=x,y=y))
            mm=((x,y),(x+80,y),(x+80,y+8),(x,y+8))
            px=tuple((a*1000/210,b*1414/297) for a,b in mm)
            regions.append(CanonicalOcrRegion(rid,text,.9,px,
                dict(x=px[0][0],y=px[0][1],width=80*1000/210,height=8*1414/297),mm,
                dict(x=x,y=y,width=80,height=8)))
        identity['pages'].append(dict(page=n,page_id=str(uuid.uuid4()),width_mm=210,height_mm=297,items=items))
        prefix=f'pages/page-{n:04d}/'
        results.append(OcrPageResult(n,210,297,1000,1414,300,prefix+'image.png',None,
                        prefix+'preview.png',prefix+'regions.md',tuple(regions),recognition_status='TEXT_DETECTED'))
        assets.update({prefix+'image.png':png,prefix+'preview.png':png,prefix+'regions.md':listing})
    source_identity=dict(identity,pages=[dict(p,items=[]) for p in identity['pages']])
    sdk=ReviewSdk(None)
    sdk.create(source_identity,hashlib.sha256(encoded(source_identity)).hexdigest(),root/'source.xdw')
    assets['source/source.xdw']=root/'source.xdw'
    result=OcrDocumentResult(str(uuid.uuid4()),dict(type='xdw',path='source/source.xdw',original_path=str(root/'source.xdw'),
        sha256=sha256(root/'source.xdw'),page_count=pages),dict(engine='synthetic-review-ab',ocr_executed=False),tuple(results),schema_version='1.1')
    save_ocr_result(result,root/'canonical',assets=assets)
    write(root/'identity.json',identity)
    write(root/'fixture.json',dict(synthetic=True,ocr_executed=False,pages=pages,items_per_page=20))


def worker(root, identity_path, variant, baseline_sdk=None):
    from docuworks_integrations._reviewed_sdk import ReviewSdk, encoded
    # Baseline has no recorder; use candidate's observer module explicitly in runner mode.
    from docuworks_integrations._performance import Recorder, measure
    if baseline_sdk:
        import importlib.util
        spec=importlib.util.spec_from_file_location('docuworks_integrations._baseline_reviewed_sdk',baseline_sdk)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        ReviewSdk=module.ReviewSdk
    root.mkdir(parents=True, exist_ok=False)
    identity=json.loads(identity_path.read_text(encoding='utf-8'))
    digest=hashlib.sha256(encoded(identity)).hexdigest()
    sdk=ReviewSdk(None)
    with Recorder(variant=variant, synthetic=True, ocr_executed=False,
                  sdk_version=sdk.api.runtime_info.version_text,dll_sha256=sdk.api.runtime_info.dll_sha256) as recorder:
        with measure('review.create'):
            create=sdk.create if variant in ('A','baseline') else sdk.create_page_join
            create(identity,digest,root/'initial.xdw')
        with measure('review.inspect'):
            snapshot=sdk.inspect(root/'initial.xdw')
        common=dict(review_id=identity['review_id'],identity_sha256=digest)
        assert json.loads(snapshot['identity'])==common
        assert len(snapshot['pages'])==len(identity['pages'])
        with measure('verification.background_and_content'):
            with sdk.api.open_document(root/'initial.xdw') as doc:
                for actual,expected in zip(snapshot['pages'],identity['pages']):
                    assert actual['page']==expected['page']
                    assert actual['width_mm']==expected['width_mm'] and actual['height_mm']==expected['height_mm']
                    assert actual['rotation']==0
                    assert json.loads(actual['identity'])==dict(common,page_id=expected['page_id'])
                    assert len(actual['items'])==len(expected['items'])
                    backgrounds=[a.get_standard_attribute_raw('%BackColor') for a in doc.page(actual['page']).annotations()]
                    for item,source,bg in zip(actual['items'],expected['items'],backgrounds):
                        assert bg==65793
                        item['back_color']=bg
                        assert item['text']==source['text'] and item['x']==source['x'] and item['y']==source['y']
                        assert item['rotation']==0 and item['direction']==0 and item['font_size']==12
                        assert item['fore_color']==255 and item['word_wrap'] is False
                        assert json.loads(item['identity'])==dict(common,annotation_id=source['annotation_id'],region_id=source['region_id'])
    encoded_snapshot=json.dumps(jsonable(snapshot),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    (root/'snapshot.json').write_bytes(encoded_snapshot)
    recorder.write(root,status='COMPLETE',snapshot_sha256=hashlib.sha256(encoded_snapshot).hexdigest(),
        xdw_bytes=(root/'initial.xdw').stat().st_size,pages=len(identity['pages']),
        items=sum(len(p['items']) for p in identity['pages']))


def small(root):
    from reviewed_fixture import create_fixture
    from docuworks_integrations import create_review_session,import_reviewed_result,load_review_session
    from docuworks_integrations.results import sha256
    from docuworks_integrations._reviewed_sdk import ReviewSdk
    from docuworks_ctypes import OpenMode
    from unittest.mock import patch
    root.mkdir(parents=True,exist_ok=False)
    run=create_fixture(root/'Japanese mixed fixture',pages=3)
    original={str(p.relative_to(run.root)):sha256(p) for p in run.root.rglob('*') if p.is_file()}
    records=[]
    for mode in ('document','page_join'):
        session=create_review_session(run.root,root/mode,review_creation_mode=mode)
        edited=root/(mode+'-edited.xdw'); shutil.copyfile(session.review_xdw,edited)
        sdk=ReviewSdk(None)
        with sdk.api.open_document(edited,mode=OpenMode.UPDATE) as doc:
            first=next(iter(doc.page(1).annotations()))
            first.set_standard_attribute('%Text','校正済みの日本語')
            doc.save()
        for validation in ('strict','identity'):
            result=import_reviewed_result(session.root,edited,root/(mode+'-'+validation),validation_mode=validation)
            assert result.pages[0]['items'][0]['text']=='校正済みの日本語'
            if validation=='strict':
                assert all(i['origin']['status']=='matched' for p in result.pages for i in p['items'])
            else:
                assert all(i['origin_evidence']['status']=='matched' for p in result.pages for i in p['items'])
        assert load_review_session(session.root)==session
        records.append(dict(mode=mode,edited_import_strict=True,edited_import_identity=True))
    # The real native implementation is faulted at distinct boundaries; no output may publish.
    failures=[]
    for fault in ('_blank','_populate','_merge','save','interrupt'):
        destination=root/('failed-'+fault)
        target='docuworks_ctypes.document.Document.save' if fault=='save' else 'docuworks_integrations._reviewed_sdk.ReviewSdk.'+('_populate' if fault=='interrupt' else fault)
        error=KeyboardInterrupt() if fault=='interrupt' else RuntimeError('injected '+fault)
        with patch(target,side_effect=error):
            try: create_review_session(run.root,destination,review_creation_mode='page_join')
            except (RuntimeError,KeyboardInterrupt): pass
            else: raise AssertionError('failure was not raised')
        assert not destination.exists()
        failures.append(fault)
    assert original=={str(p.relative_to(run.root)):sha256(p) for p in run.root.rglob('*') if p.is_file()}
    write(root/'validation.json',dict(synthetic=True,ocr_executed=False,mixed_sizes=True,blank_page=True,
          cases=records,injected_failures=failures,failed_outputs_not_published=True,canonical_unchanged=True))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=('fixture','worker','small'))
    p.add_argument('--repo',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--pages',type=int,default=256);p.add_argument('--identity',type=Path)
    p.add_argument('--variant',choices=('A','B','baseline'));p.add_argument('--baseline-sdk',type=Path)
    args=p.parse_args()
    sys.path[:0]=[str(args.repo/'packages/docuworks-integrations'),str(args.repo/'packages/docuworks-ctypes'),
                  str(args.repo/'packages/docuworks-integrations/tests')]
    if args.action=='fixture': fixture(args.output,args.pages)
    elif args.action=='small': small(args.output)
    else: worker(args.output,args.identity,args.variant,args.baseline_sdk)


if __name__=='__main__': main()
