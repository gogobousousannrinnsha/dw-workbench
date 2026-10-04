"""Sequential OCR and independent consumers, journalled per document and stage."""
from contextlib import redirect_stdout
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import time
import uuid

from .settings import Settings
from . import __version__
from .discovery import collect_documents, check_source
from .derivatives import annotate_rectangles, render_text_maps, resolve_font, IntegrityError
from .results import load_ocr_result, export_jsonl, sha256
from ._storage import atomic_json, check_publish_access, note
from ._performance import measure


def _journal(folder, payload):
    atomic_json(folder, payload)


def process_documents(inputs, output_dir, runs_dir, model_root, *, settings=None,
                      dll_path=None, excluded=(), engine=None, review=False,
                      review_creation_mode='document'):
    """Fresh job directories; shared engine; all pages in one run per document.

    Returns a job dictionary with exit_code 0/1/130. Invalid preflight raises.
    Known document-local SDK failures continue; shared/unknown/integrity failures stop.
    """
    settings = settings or Settings()
    if not isinstance(settings,Settings): raise TypeError('settings must be Settings')
    if type(review) is not bool: raise TypeError('review must be bool')
    if review_creation_mode not in ('document', 'page_join'):
        raise ValueError('review_creation_mode must be document or page_join')
    stages = ('ocr', 'review', 'rectangles', 'text_maps', 'jsonl') if review else ('ocr', 'rectangles', 'text_maps', 'jsonl')
    output, runs = Path(output_dir).resolve(), Path(runs_dir).resolve()
    if output.is_relative_to(runs) or runs.is_relative_to(output):
        raise ValueError('job output and runs directories must be separate')
    for p in (output,runs):
        if p.exists(): raise FileExistsError(p)
    sources = collect_documents(inputs,recursive=settings.recursive,excluded=(*excluded,output,runs))
    sample = runs/'.recognition-000000000000/pages/page-999999/image.bmp'
    if len(str(sample).encode('utf-16-le'))//2 > 255:
        raise ValueError('SDK image path exceeds 255 UTF-16 units; move DW-OCR to a shorter writable path')
    if sources: resolve_font(settings.font or None)
    output.mkdir(parents=True); runs.mkdir(parents=True)
    started = time.perf_counter()
    records = [dict(document_id=f'doc-{i:06d}', source_name=p.name,
        source_diagnostic_path=str(p),run_dir=Path(os.path.relpath(runs/f'doc-{i:06d}',output)).as_posix(),
        output_dir=f'doc-{i:06d}',ocr='PENDING',rectangles='PENDING',text_maps='PENDING',
        jsonl='PENDING' if settings.jsonl else 'DISABLED',errors=[]) for i,p in enumerate(sources,1)]
    if review:
        for record in records: record.update(review='PENDING', review_dir=record['output_dir']+'/review-session')
    job = dict(schema='dw-ocr-job',schema_version='1.1' if review else '1.0',integration_version=__version__,
        job_id=str(uuid.uuid4()),status='RUNNING',started_at=datetime.now(timezone.utc).isoformat(),
        settings=settings.to_dict(),documents=records,exit_code=1)
    _journal(output,job)
    fatal = None
    active = None
    try:
        if sources:
            # Recognition publishes by renaming a directory. Detect a denied operation
            # before model initialization or any expensive document processing.
            check_publish_access(runs)
        if sources:
            from .recognition import ocr_xdw_pages
            from .failures import failure_scope, SourceChangedError
            if engine is None:
                from .paddle import PaddleOcrEngine
                engine = PaddleOcrEngine(model_root)
        for source,record in zip(sources,records):
            print(f"Document {record['document_id']}: {source.name}",file=sys.stderr)
            doc_output=output/record['output_dir']; doc_output.mkdir()
            run=runs/record['document_id']
            t=time.perf_counter()
            for stage in stages:
                if record[stage]=='DISABLED': continue
                if stage!='ocr' and record['ocr']!='SUCCEEDED': continue
                active=(record,stage); record[stage]='RUNNING'; _journal(output,job)
                observation = measure(stage, document_id=record['document_id'])
                observation.__enter__()
                stage_error = None
                try:
                    if stage=='ocr':
                        try:
                            check_source(source,Path(source.anchor))
                        except PermissionError as exc:
                            raise IntegrityError('source became inaccessible or a reparse point') from exc
                        initial=sha256(source)
                        with redirect_stdout(sys.stderr):
                            ocr_xdw_pages(source,run,model_root,pages=None,dpi=settings.dpi,
                                          dll_path=dll_path,engine=engine)
                        result=load_ocr_result(run)
                        if initial!=result.source['sha256'] or sha256(source)!=initial:
                            raise IntegrityError('source changed during OCR')
                        record.update(run_id=result.run_id,manifest_sha256=result.manifest_sha256,
                                      source_sha256=initial)
                    elif stage=='review':
                        from .reviewed import create_review_session
                        review_options = {} if review_creation_mode == 'document' else dict(review_creation_mode=review_creation_mode)
                        session=create_review_session(run,doc_output/'review-session',dll_path=dll_path,**review_options)
                        record.update(review_id=session.review_id,review_manifest_sha256=session.manifest_sha256)
                    elif stage=='rectangles':
                        annotate_rectangles(run,doc_output/'annotated.xdw',dll_path=dll_path,
                            padding_mm=settings.padding_mm,minimum_mm=settings.minimum_mm,
                            min_confidence=settings.min_confidence,color=settings.color,
                            report_path=doc_output/'rectangles-report.json')
                    elif stage=='text_maps':
                        render_text_maps(run,doc_output/'text-maps',font=settings.font or None,
                                         min_confidence=settings.min_confidence)
                    else: export_jsonl(load_ocr_result(run),doc_output/'regions.jsonl')
                    record[stage]='SUCCEEDED'
                except (Exception,KeyboardInterrupt) as exc:
                    stage_error = exc
                    record[stage]='FAILED'
                    scope=getattr(exc,'_ocr_failure_scope',failure_scope(exc,'render' if stage in ('rectangles','review') else 'source'))
                    if isinstance(exc,(IntegrityError,SourceChangedError)) or getattr(exc,'_ocr_cleanup_failed',False):
                        scope='batch'
                    record['errors'].append(dict(stage=stage,type=type(exc).__name__,message=str(exc),scope=scope,
                        notes=getattr(exc,'__notes__',[]),diagnostics=getattr(exc,'_ocr_diagnostics',None)))
                    if scope!='document': raise
                finally:
                    observation.__exit__(type(stage_error) if stage_error else None, stage_error,
                                         stage_error.__traceback__ if stage_error else None)
                    record['elapsed_seconds']=time.perf_counter()-t
                    primary=sys.exc_info()[1]
                    try:
                        _journal(output,job)
                    except OSError as journal_error:
                        if primary is not None:
                            note(primary, f'Job journal save also failed: {output}: {journal_error}')
                            raise primary
                        raise
            active=None
    except (Exception,KeyboardInterrupt) as exc:
        fatal=exc
        job['error']=dict(type=type(exc).__name__,message=str(exc),notes=getattr(exc,'__notes__',[]))
        if active and active[0][active[1]]=='RUNNING': active[0][active[1]]='FAILED'
    job['counts']={s:{state:sum(r[s]==state for r in records)
                     for state in ('SUCCEEDED','FAILED','PENDING','DISABLED')}
                   for s in stages}
    failed=any(r[s]=='FAILED' for r in records for s in stages)
    job.update(status='INTERRUPTED' if isinstance(fatal,KeyboardInterrupt) else 'FAILED' if fatal else
               'PARTIAL_FAILED' if failed else 'COMPLETE' if records else 'NO_INPUT',
               exit_code=130 if isinstance(fatal,KeyboardInterrupt) else 1 if fatal or failed else 0,
               elapsed_seconds=time.perf_counter()-started,finished_at=datetime.now(timezone.utc).isoformat())
    try:
        _journal(output,job)
    except OSError as journal_error:
        if fatal is not None:
            note(fatal, f'Final job journal save also failed: {output}: {journal_error}')
            raise fatal
        raise
    return job
