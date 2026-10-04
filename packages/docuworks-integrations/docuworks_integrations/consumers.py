"""Saved OCR result consumers. GPU libraries are never imported here."""
from pathlib import Path
from .results import load_ocr_result, get_region, sha256, bundle_path, write_json


def mark_region(run_dir, region_id, output_xdw, *, dry_run=False, dll_path=None, input_xdw=None):
    result=load_ocr_result(run_dir)
    region=get_region(result,region_id)
    page=next(p for p in result.pages if any(r.id==region.id for r in p.regions))
    original=Path(input_xdw or result.source['original_path']).resolve()
    if sha256(original)!=result.source['sha256']: raise RuntimeError('original XDW changed since preview')
    from .models import OcrRegion, PixelRect, PixelPoint
    from .transforms import PageTransform
    from .planning import build_marker_plan
    from .executor import execute_plan
    old_region=OcrRegion(region.text,PixelRect(**region.bbox_px),region.confidence,
                         tuple(PixelPoint(*p) for p in region.polygon_px))
    plan=build_marker_plan(bundle_path(result.root,page.image),old_region,
        PageTransform(page.image_width_px,page.image_height_px,page.page_width_mm,page.page_height_mm),page=page.page)
    output=Path(output_xdw).resolve()
    if output.is_relative_to(result.root): raise ValueError('marker output must be outside immutable bundle')
    report_path=output.with_suffix('.report.json')
    if report_path.exists() and not dry_run: raise FileExistsError(report_path)
    def recheck():
        current=load_ocr_result(run_dir)
        if current.manifest_sha256!=result.manifest_sha256: raise RuntimeError('manifest changed during marking')
        if sha256(original)!=result.source['sha256']: raise RuntimeError('original changed during marking')
    report=execute_plan(plan,bundle_path(result.root,result.source['path']),output,dry_run=dry_run,
        dll_path=dll_path or result.ocr.get('dll_path'),precommit_check=recheck)
    recheck()
    payload=dict(run_id=result.run_id,region_id=region.id,text=region.text,
        original_xdw=str(original),original_sha256=result.source['sha256'],
        run_manifest_sha256=result.manifest_sha256,viewer_status='PENDING_MANUAL_REVIEW',
        plan=plan.to_dict(),execution=report.to_dict())
    if not dry_run: write_json(report_path,payload)
    return payload
