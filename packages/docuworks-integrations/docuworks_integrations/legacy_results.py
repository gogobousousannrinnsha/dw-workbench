"""Read-only adapter for 0.2.0 bundles; no OCR or SDK imports."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import uuid

from .results import (read_json, sha256, bundle_path, canonical_region, OcrPageResult,
    OcrDocumentResult, validate_result, save_ocr_result, load_ocr_result)


def load_legacy_result(root):
    m=read_json(root/'run.json')
    if m.get('schema_version')!=1 or m.get('status')!='READY_FOR_SELECTION': raise ValueError('unsupported legacy run')
    required={'source.xdw','page.png','page-info.json','regions.json','preview.png','regions.md'}
    if not required.issubset(m['files']): raise ValueError('incomplete legacy run')
    for name,h in m['files'].items():
        if '/' in name or sha256(bundle_path(root,name))!=h: raise RuntimeError(f'legacy input changed: {name}')
    meta=read_json(root/'page-info.json')
    if m['source_sha256']!=meta['source_sha256'] or m['files']['source.xdw']!=m['source_sha256']:
        raise ValueError('legacy source identity mismatch')
    page=meta['page']
    sx,sy=meta['page_width_mm']/meta['pixel_width'],meta['page_height_mm']/meta['pixel_height']
    rows=read_json(root/'regions.json')['regions']
    regions=[]
    for i,r in enumerate(rows,1):
        if r.get('region_id',i)!=i: raise ValueError('legacy region ordering mismatch')
        b=r['bbox']
        rect=SimpleNamespace(**b,right=b['x']+b['width'],bottom=b['y']+b['height'])
        poly=tuple(SimpleNamespace(**p) for p in r['polygon']) if r.get('polygon') else None
        regions.append(canonical_region(SimpleNamespace(bbox=rect,polygon=poly,text=r['text'],confidence=r.get('confidence')),page,i,sx,sy))
    p=OcrPageResult(page,meta['page_width_mm'],meta['page_height_mm'],meta['pixel_width'],meta['pixel_height'],
        meta.get('render_dpi',300),'page.png','ocr-raw.json' if 'ocr-raw.json' in m['files'] else None,
        'preview.png','regions.md',tuple(regions))
    digest=sha256(root/'run.json')
    result=OcrDocumentResult(str(uuid.uuid5(uuid.NAMESPACE_URL,'legacy-ocr:'+digest)),
        dict(type='xdw',path='source.xdw',original_path=m['source_path'],sha256=m['source_sha256'],
             page_count=meta.get('page_count'),page_count_provenance='recorded' if 'page_count' in meta else 'unknown-in-legacy'),
        dict(engine='legacy-recorded',legacy_run_sha256=digest,python=m.get('python'),
             device=m.get('device'),elapsed_seconds=m.get('elapsed_seconds'),dll_path=meta.get('dll_path')),
        (p,),root=root,manifest_sha256=digest)
    validate_result(result)
    return result


def convert_ocr_run(run_dir, output_dir, *, ocr_metadata=None, new_run_id=None):
    original=load_ocr_result(run_dir)
    if Path(output_dir).resolve().is_relative_to(original.root):
        raise ValueError('conversion output must be outside the source bundle')
    assets={}
    source=dict(original.source,path='source/source.xdw')
    assets[source['path']]=bundle_path(original.root,original.source['path'])
    pages=[]
    for p in original.pages:
        prefix=f'pages/page-{p.page:04d}/'
        names=dict(image=prefix+'image.png',raw=prefix+'raw-paddle.json' if p.raw else None,
                   preview=prefix+'preview.png',listing=prefix+'regions.md')
        for key,name in names.items():
            if name: assets[name]=bundle_path(original.root,getattr(p,key))
        pages.append(replace(p,**names))
    converted=replace(original,source=source,pages=tuple(pages),root=None,manifest_sha256=None,
                      ocr=ocr_metadata or original.ocr,run_id=new_run_id or original.run_id)
    # Re-check before publication; do not require the original external path for conversion.
    if load_ocr_result(run_dir).manifest_sha256!=original.manifest_sha256: raise RuntimeError('legacy manifest changed')
    expected={name:sha256(path) for name,path in assets.items()}
    load_ocr_result(run_dir)
    result=save_ocr_result(converted,output_dir,assets=assets,expected_hashes=expected)
    return result
