"""Versioned OCR bundles. This module uses only the Python standard library."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path, PurePosixPath
import hashlib
import json
import math
import re
import shutil
import uuid
from ._storage import owned_directory, publish_new, require_public_result

SCHEMA = 'docuworks-ocr-result'
VERSION = '1.0'
SUPPORTED_VERSIONS = ('1.0', '1.1')


def sha256(path):
    with Path(path).open('rb') as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024*1024), b''): digest.update(chunk)
        return digest.hexdigest()


def read_json(path):
    def unique(pairs):
        d = {}
        for k, v in pairs:
            if k in d: raise ValueError(f'duplicate JSON key: {k}')
            d[k] = v
        return d
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def bundle_path(root, name):
    if not isinstance(name, str) or '\\' in name or ':' in name:
        raise ValueError('bundle paths must be relative POSIX paths')
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or not p.parts or str(p) != name:
        raise ValueError('invalid bundle path')
    root = Path(root).resolve()
    dest = root.joinpath(*p.parts).resolve()
    if not dest.is_relative_to(root): raise ValueError('bundle path escapes root')
    return dest


def number(value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('coordinate must be a finite number')
    if positive and value <= 0: raise ValueError('dimension must be positive')
    return value


def positive_int(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError('expected positive integer')
    return value


@dataclass(frozen=True)
class CanonicalOcrRegion:
    id: str
    text: str
    confidence: float | None
    polygon_px: tuple
    bbox_px: dict
    polygon_mm: tuple
    bbox_mm: dict

    def __post_init__(self):
        object.__setattr__(self, 'polygon_px', tuple(tuple(p) for p in self.polygon_px))
        object.__setattr__(self, 'polygon_mm', tuple(tuple(p) for p in self.polygon_mm))


@dataclass(frozen=True)
class OcrPageResult:
    page: int
    page_width_mm: float
    page_height_mm: float
    image_width_px: int
    image_height_px: int
    render_dpi: int
    image: str
    raw: str | None
    preview: str
    listing: str
    regions: tuple[CanonicalOcrRegion, ...]
    coordinate_system: str = 'top-left-x-right-y-down'
    rotation: int = 0
    recognition_status: str | None = None


@dataclass(frozen=True)
class OcrDocumentResult:
    run_id: str
    source: dict
    ocr: dict
    pages: tuple[OcrPageResult, ...]
    schema_version: str = VERSION
    root: Path | None = field(default=None, repr=False, compare=False)
    manifest_sha256: str | None = field(default=None, repr=False, compare=False)


def canonical_region(region, page, ordinal, sx, sy):
    """Convert an engine OcrRegion without importing any engine or SDK."""
    b = region.bbox
    points = [(p.x, p.y) for p in region.polygon] if region.polygon else [
        (b.x,b.y),(b.right,b.y),(b.right,b.bottom),(b.x,b.bottom)]
    bbox = dict(x=b.x,y=b.y,width=b.width,height=b.height)
    return CanonicalOcrRegion(f'p{page:04d}-r{ordinal:06d}', region.text, region.confidence,
        tuple(points), bbox, tuple((x*sx,y*sy) for x,y in points),
        dict(x=b.x*sx,y=b.y*sy,width=b.width*sx,height=b.height*sy))


def validate_result(result):
    if result.schema_version not in SUPPORTED_VERSIONS: raise ValueError('unsupported OCR schema version')
    uuid.UUID(result.run_id)
    source = result.source
    if source.get('type') != 'xdw': raise ValueError('unsupported source type')
    if not re.fullmatch('[0-9a-f]{64}', source.get('sha256','')): raise ValueError('invalid source hash')
    count = source.get('page_count')
    if count is not None: positive_int(count)
    if not result.pages: raise ValueError('no processed pages')
    seen_pages, seen_ids = set(), set()
    for p in result.pages:
        positive_int(p.page)
        if p.page in seen_pages or (count is not None and p.page > count): raise ValueError('invalid page number')
        seen_pages.add(p.page)
        positive_int(p.image_width_px); positive_int(p.image_height_px)
        number(p.page_width_mm, positive=True); number(p.page_height_mm, positive=True)
        if p.render_dpi not in (300,600) or isinstance(p.render_dpi,bool): raise ValueError('unsupported dpi')
        if p.rotation != 0 or p.coordinate_system != 'top-left-x-right-y-down': raise ValueError('unsupported coordinates')
        if result.schema_version == '1.0':
            if not p.regions: raise ValueError('OCR found no text')
            if p.recognition_status is not None: raise ValueError('status requires schema 1.1')
        elif p.recognition_status != ('TEXT_DETECTED' if p.regions else 'NO_TEXT_DETECTED'):
            raise ValueError('recognition status does not match regions')
        sx,sy = p.page_width_mm/p.image_width_px,p.page_height_mm/p.image_height_px
        for ordinal,r in enumerate(p.regions,1):
            if r.id != f'p{p.page:04d}-r{ordinal:06d}' or r.id in seen_ids: raise ValueError('invalid or duplicate region ID')
            seen_ids.add(r.id)
            if not isinstance(r.text,str) or not r.text.strip(): raise ValueError('empty OCR text')
            if r.confidence is not None and not 0 <= number(r.confidence) <= 1: raise ValueError('invalid confidence')
            if len(r.polygon_px)!=4 or len(r.polygon_mm)!=4: raise ValueError('four corners required')
            for px,mm in zip(r.polygon_px,r.polygon_mm):
                if len(px)!=2 or len(mm)!=2: raise ValueError('xy pair required')
                x,y = map(number,px)
                if not 0<=x<=p.image_width_px or not 0<=y<=p.image_height_px: raise ValueError('region outside image')
                if abs(number(mm[0])-x*sx)>1e-7 or abs(number(mm[1])-y*sy)>1e-7: raise ValueError('px/mm mismatch')
            points=r.polygon_px
            crosses=[]
            for i in range(4):
                a,b,c=points[i],points[(i+1)%4],points[(i+2)%4]
                crosses.append((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]))
            if not (all(c>0 for c in crosses) or all(c<0 for c in crosses)): raise ValueError('invalid quadrilateral')
            xs,ys=zip(*points)
            expected=dict(x=min(xs),y=min(ys),width=max(xs)-min(xs),height=max(ys)-min(ys))
            for key,v in expected.items():
                if set(r.bbox_px)!=set(expected) or set(r.bbox_mm)!=set(expected): raise ValueError('invalid bbox keys')
                if abs(number(r.bbox_px[key])-v)>1e-7: raise ValueError('polygon/bbox mismatch')
                factor=sx if key in ('x','width') else sy
                if abs(number(r.bbox_mm[key])-v*factor)>1e-7: raise ValueError('bbox px/mm mismatch')


def _page_from_dict(data):
    data=dict(data)
    data['regions']=tuple(CanonicalOcrRegion(**r) for r in data['regions'])
    return OcrPageResult(**data)


def load_ocr_result(run_dir):
    root=Path(run_dir).resolve()
    require_public_result(root)
    return _load_saved_result(root)


def _load_saved_result(root):
    """Validate saved bytes, including private staging before atomic publication."""
    if not (root/'manifest.json').exists():
        from .legacy_results import load_legacy_result
        return load_legacy_result(root)
    m=read_json(root/'manifest.json')
    if m.get('schema')!=SCHEMA or m.get('schema_version') not in SUPPORTED_VERSIONS or m.get('status')!='COMPLETE':
        raise ValueError('unsupported or incomplete OCR result')
    files=m['files']
    for name,h in files.items():
        if not re.fullmatch('[0-9a-f]{64}',h): raise ValueError('invalid file hash')
        if sha256(bundle_path(root,name))!=h: raise RuntimeError(f'bundle input changed: {name}')
    required={m['source']['path']}
    pages=[]
    for entry in m['pages']:
        path=entry['result']
        required.add(path)
        p=_page_from_dict(read_json(bundle_path(root,path)))
        if entry['page']!=p.page: raise ValueError('page reference mismatch')
        required.update((p.image,p.preview,p.listing))
        if p.raw: required.add(p.raw)
        pages.append(p)
    if not required.issubset(files): raise ValueError('unhashed required file')
    if files[m['source']['path']]!=m['source']['sha256']: raise ValueError('source identity mismatch')
    result=OcrDocumentResult(m['run_id'],m['source'],m['ocr'],tuple(pages),m['schema_version'],root,sha256(root/'manifest.json'))
    validate_result(result)
    return result


def save_ocr_result(result, output_dir, *, assets=None, expected_hashes=None):
    """Publish a new bundle. assets maps relative bundle paths to existing files."""
    validate_result(result)
    if result.root is not None:
        if load_ocr_result(result.root).manifest_sha256 != result.manifest_sha256:
            raise RuntimeError('result changed since loading')
    output=Path(output_dir).resolve()
    require_public_result(output)
    if result.root is not None and output.is_relative_to(result.root):
        raise ValueError('new bundle must be outside the source bundle')
    if output.exists(): raise FileExistsError(output)
    if not output.parent.is_dir(): raise FileNotFoundError(output.parent)
    with owned_directory(output.parent, '.ocr-') as staging:
        paths={result.source['path']}
        for p in result.pages:
            paths.update((p.image,p.preview,p.listing))
            if p.raw: paths.add(p.raw)
        for name in paths:
            dest=bundle_path(staging,name)
            src=Path(assets[name]) if assets is not None else bundle_path(result.root,name)
            expected = expected_hashes[name] if expected_hashes is not None else sha256(src)
            dest.parent.mkdir(parents=True,exist_ok=True)
            with src.open('rb') as a, dest.open('xb') as b: shutil.copyfileobj(a,b)
            if sha256(src)!=expected or sha256(dest)!=expected: raise RuntimeError('asset changed during copy')
        entries=[]
        for p in result.pages:
            name=f'pages/page-{p.page:04d}/result.json'
            path=bundle_path(staging,name)
            path.parent.mkdir(parents=True,exist_ok=True)
            data=asdict(p)
            if result.schema_version == '1.0': data.pop('recognition_status')
            write_json(path,data)
            entries.append(dict(page=p.page,result=name))
        files={p.relative_to(staging).as_posix():sha256(p) for p in staging.rglob('*') if p.is_file()}
        write_json(staging/'manifest.json',dict(schema=SCHEMA,schema_version=result.schema_version,status='COMPLETE',
            run_id=result.run_id,source=result.source,ocr=result.ocr,pages=entries,files=files))
        _load_saved_result(staging)
        publish_new(staging, output)
    return load_ocr_result(output)


def get_region(result, region_id):
    validate_result(result)
    if isinstance(region_id,bool): raise ValueError('invalid region ID')
    if isinstance(region_id,int) or (isinstance(region_id,str) and region_id.isdecimal()):
        if len(result.pages)!=1: raise ValueError('integer selection requires one processed page')
        n=int(region_id)
        if n<1: raise ValueError('invalid region ID')
        region_id=f'p{result.pages[0].page:04d}-r{n:06d}'
    for page in result.pages:
        for region in page.regions:
            if region.id==region_id: return region
    raise ValueError('region ID not found')


def export_jsonl(result, output):
    if result.root is None: raise ValueError('export requires a saved result')
    current=load_ocr_result(result.root)
    if current.manifest_sha256!=result.manifest_sha256: raise RuntimeError('result changed since loading')
    output=Path(output).resolve()
    if output.is_relative_to(result.root): raise ValueError('derived output must be outside immutable bundle')
    with output.open('x',encoding='utf-8') as f:
        for p in sorted(current.pages, key=lambda page: page.page):
            for r in p.regions:
                f.write(json.dumps(dict(run_id=current.run_id,manifest_sha256=current.manifest_sha256,
                    page=p.page,**asdict(r)),ensure_ascii=False,allow_nan=False)+'\n')
    return output
