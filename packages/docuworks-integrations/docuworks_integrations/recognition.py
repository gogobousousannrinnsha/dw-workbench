"""Sequential multi-page producer; publishes only complete OCR Result 1.1 bundles."""
from pathlib import Path
from dataclasses import asdict
from contextlib import redirect_stdout
import importlib.metadata as md
import platform
import shutil
import sys
import time
import uuid
from .results import (read_json, write_json, sha256, canonical_region, OcrPageResult,
    OcrDocumentResult, validate_result, _load_saved_result)
from ._storage import publish_new, require_public_result, note
from .page_selection import resolve_pages
from .rendering import XdwRenderer
from .failures import SourceChangedError, failure_scope


def ocr_xdw(input_xdw, run_dir, model_root, *, page=1, dpi=300, dll_path=None, engine=None):
    return ocr_xdw_pages(input_xdw, run_dir, model_root, pages=(page,), dpi=dpi, dll_path=dll_path, engine=engine)


def ocr_xdw_pages(input_xdw, run_dir, model_root, *, pages=None, dpi=300, dll_path=None, engine=None):
    source = Path(input_xdw).resolve()
    output = Path(run_dir).resolve()
    require_public_result(output)
    if output.exists(): raise FileExistsError(output)
    if dpi not in (300, 600) or isinstance(dpi, bool): raise ValueError('dpi must be 300 or 600')
    if not source.is_file(): raise FileNotFoundError(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / ('.recognition-' + uuid.uuid4().hex[:12])
    (staging/'source').mkdir(parents=True)
    copy = staging/'source/source.xdw'
    started = time.perf_counter()
    completed, timings, page_results, selected = [], [], [], []
    current_page, phase = None, 'copy'
    try:
        phase = 'source'
        source_hash = sha256(source)
        phase = 'copy'
        with source.open('rb') as a, copy.open('xb') as b: shutil.copyfileobj(a,b)
        if sha256(copy)!=source_hash or sha256(source)!=source_hash: raise SourceChangedError('source changed during copy')
        phase = 'selection'
        with XdwRenderer(copy, dll_path) as renderer:
            selected = resolve_pages(pages, renderer.page_count)
            # Check all SDK output paths before rendering or model initialization.
            for n in selected:
                bmp = staging/f'pages/page-{n:04d}/image.bmp'
                if len(str(bmp).encode('utf-16-le'))//2 > 255: raise ValueError('SDK image path exceeds 255 UTF-16 code units')
            source_info = dict(type='xdw',path='source/source.xdw',original_path=str(source),
                sha256=source_hash,page_count=renderer.page_count,page_count_provenance='recorded')
            if engine is None:
                from .paddle import PaddleOcrEngine
                engine = PaddleOcrEngine(model_root)
            from ._preview import create_preview
            for index, n in enumerate(selected, 1):
                current_page, phase = n, 'render'
                page_started = time.perf_counter()
                prefix=f'pages/page-{n:04d}/'
                folder=staging/prefix
                folder.mkdir(parents=True)
                print(f'Page {n} ({index}/{len(selected)}): rendering',file=sys.stderr)
                dimensions=renderer.render(n,folder,dpi)
                phase='recognize'
                # Clear previous-page evidence even if the engine fails before returning.
                if hasattr(engine,'last_raw'): engine.last_raw=None
                try:
                    with redirect_stdout(sys.stderr):
                        regions=tuple(engine.recognize(folder/'image.png'))
                finally:
                    if getattr(engine,'last_raw',None) is not None:
                        write_json(folder/'raw-paddle.json',engine.last_raw)
                phase='validate'
                sx=dimensions['page_width_mm']/dimensions['image_width_px']
                sy=dimensions['page_height_mm']/dimensions['image_height_px']
                canonical=tuple(canonical_region(r,n,i,sx,sy) for i,r in enumerate(regions,1))
                page_result=OcrPageResult(page=n,**dimensions,render_dpi=dpi,image=prefix+'image.png',
                    raw=prefix+'raw-paddle.json' if (folder/'raw-paddle.json').exists() else None,
                    preview=prefix+'preview.png',listing=prefix+'regions.md',regions=canonical,
                    recognition_status='TEXT_DETECTED' if regions else 'NO_TEXT_DETECTED')
                validate_result(OcrDocumentResult(str(uuid.uuid4()),source_info,{},(page_result,),schema_version='1.1'))
                phase='save-page'
                create_preview(folder/'image.png',regions,folder)
                with (folder/'regions.md').open('a',encoding='utf-8') as listing:
                    listing.write('\nPage '+str(n)+' / '+page_result.recognition_status+'\n')
                write_json(folder/'result.json',asdict(page_result))
                page_results.append(page_result)
                completed.append(n)
                elapsed=time.perf_counter()-page_started
                timings.append(dict(page=n,regions=len(regions),elapsed_seconds=elapsed))
                print(f'Page {n}: {len(regions)} regions, {elapsed:.3f}s',file=sys.stderr)
                del regions, canonical
            packages={}
            for name in ('paddleocr','paddlex','paddlepaddle-gpu'):
                try: packages[name]=md.version(name)
                except md.PackageNotFoundError: packages[name]=None
            models={name:{p.name:sha256(p) for p in sorted((Path(model_root)/name).glob('*')) if p.is_file()}
                    for name in ('PP-OCRv6_medium_det','PP-OCRv6_medium_rec')}
            provenance=dict(engine=type(engine).__name__,packages=packages,models=models,python=platform.python_version(),
                device='gpu:0' if type(engine).__name__=='PaddleOcrEngine' else 'injected',
                dll_path=renderer.dll_path,selected_pages=list(selected),page_timings=timings,
                elapsed_seconds=time.perf_counter()-started,
                preprocessing=dict(document_orientation=False,unwarping=False,textline_orientation=False))
        phase='publish'
        result=OcrDocumentResult(str(uuid.uuid4()),source_info,provenance,tuple(page_results),schema_version='1.1')
        validate_result(result)
        files={p.relative_to(staging).as_posix():sha256(p) for p in staging.rglob('*') if p.is_file()}
        manifest=dict(schema='docuworks-ocr-result',schema_version='1.1',status='COMPLETE',run_id=result.run_id,
            source=source_info,ocr=provenance,pages=[dict(page=p.page,result=f'pages/page-{p.page:04d}/result.json') for p in page_results],files=files)
        write_json(staging/'manifest.json',manifest)
        _load_saved_result(staging)
        if sha256(source)!=source_hash or sha256(copy)!=source_hash: raise SourceChangedError('original or copy changed before publication')
        publish_new(staging, output)
        return manifest
    except BaseException as exc:
        exc._ocr_phase = phase
        exc._ocr_failure_scope = 'batch' if getattr(exc, '_ocr_cleanup_failed', False) else failure_scope(exc, phase)
        # Retain diagnostics in place: do not retry a failed filesystem move.
        # Public readers reject the private staging name even if a manifest remains.
        exc._ocr_diagnostics = str(staging)
        note(exc, f'Unpublished OCR diagnostics retained at: {staging}')
        try:
            error=dict(status='FAILED',type=type(exc).__name__,message=str(exc),
                failed_page=current_page,phase=phase,failure_scope=exc._ocr_failure_scope,
                completed_pages=completed,selected_pages=list(selected),page_timings=timings,
                elapsed_seconds=time.perf_counter()-started)
            write_json(staging/'error.json',error)
            if not output.exists():
                output.mkdir()
                write_json(output/'error.json',dict(error,diagnostics='../'+staging.name))
        except OSError as diagnostic_error:
            exc._ocr_failure_scope = 'batch'
            note(exc, 'Diagnostic save failed: '+str(diagnostic_error))
        raise
