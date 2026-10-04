"""Sequential folder recognition with independent, immutable document runs."""
from contextlib import redirect_stdout
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import sys
import time
import uuid

from .failures import failure_scope
from .recognition import ocr_xdw_pages


@dataclass
class BatchDocumentResult:
    document_id: str
    source_relative_path: str
    run_dir: str
    status: str = 'PENDING'
    run_id: str | None = None
    source_sha256: str | None = None
    page_count: int | None = None
    elapsed_seconds: float = 0.0
    error: dict | None = None


@dataclass
class OcrBatchResult:
    batch_id: str
    input_dir: str
    settings: dict
    documents: list[BatchDocumentResult]
    schema: str = 'docuworks-ocr-batch'
    schema_version: str = '1.0'
    status: str = 'RUNNING'
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str | None = None
    elapsed_seconds: float = 0.0
    error: dict | None = None

    @property
    def exit_code(self):
        return 0 if self.status == 'COMPLETE' else 130 if self.status == 'INTERRUPTED' else 1

    def to_dict(self):
        return asdict(self)


from .discovery import linked as _linked, sources, check_source as _check_source


def _sources(root, recursive):
    return sources(root, recursive, link_check=_linked)


def _save(output, result):
    temporary = output / ('.batch-' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(result.to_dict(), stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output / 'batch.json')
    finally:
        if temporary.exists():
            temporary.unlink()


def _error(exc, scope):
    return dict(type=type(exc).__name__, message='\n'.join([str(exc), *getattr(exc,'__notes__',[])]), scope=scope,
                phase=getattr(exc, '_ocr_phase', None))


def ocr_folder(input_dir, batch_dir, model_root, *, recursive=False, dpi=300,
               dll_path=None, engine=None) -> OcrBatchResult:
    """OCR every XDW's full pages; known document failures continue, others stop.

    Invalid arguments raise before creating output. Runtime outcomes are returned
    and saved in batch.json. Journal write failures propagate to the caller.
    The optional engine follows OcrEngine and is reused across all documents.
    """
    input_path = Path(input_dir).expanduser().absolute()
    root, output = input_path.resolve(), Path(batch_dir).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)
    if _linked(input_path):
        raise ValueError('Input directory must not be a link or reparse point')
    if output == root or root in output.parents:
        raise ValueError('Batch output must be outside the input directory')
    if output.exists():
        raise FileExistsError(output)
    if isinstance(dpi, bool) or dpi not in (300, 600):
        raise ValueError('dpi must be 300 or 600')
    sources = _sources(root, recursive)
    if not sources:
        raise ValueError('No XDW files found')
    # Recognition uses a fixed-length staging name; validate SDK path before work.
    sample = output / 'runs/.recognition-000000000000/pages/page-0001/image.bmp'
    if len(str(sample).encode('utf-16-le')) // 2 > 255:
        raise ValueError('Batch output path is too long for the SDK (255 UTF-16 code units)')
    records = [BatchDocumentResult(f'doc-{i:06d}', source.relative_to(root).as_posix(),
                                  f'runs/doc-{i:06d}') for i, source in enumerate(sources, 1)]
    result = OcrBatchResult(str(uuid.uuid4()), str(root),
        dict(recursive=recursive, dpi=dpi, pages='all', model_root=str(Path(model_root).resolve()),
             dll_path=str(Path(dll_path).resolve()) if dll_path else None), records)
    started = time.perf_counter()
    output.mkdir(parents=True)  # No exist_ok: simultaneous invocations cannot share output.
    _save(output, result)
    try:
        if engine is None:
            from .paddle import PaddleOcrEngine
            with redirect_stdout(sys.stderr):
                engine = PaddleOcrEngine(model_root)
        for index, (source, record) in enumerate(zip(sources, records), 1):
            record.status = 'RUNNING'
            _save(output, result)
            page_started = time.perf_counter()
            print(f'Document {index}/{len(records)}: {record.source_relative_path}', file=sys.stderr)
            try:
                _check_source(source, root)
                with redirect_stdout(sys.stderr):
                    manifest = ocr_xdw_pages(source, output / record.run_dir, model_root,
                        pages=None, dpi=dpi, dll_path=dll_path, engine=engine)
                record.run_id = manifest['run_id']
                record.source_sha256 = manifest['source']['sha256']
                record.page_count = manifest['source']['page_count']
                record.status = 'SUCCEEDED'
            except (Exception, KeyboardInterrupt) as exc:
                scope = getattr(exc, '_ocr_failure_scope', failure_scope(exc, 'source'))
                record.status = 'FAILED'
                record.error = _error(exc, scope)
                if scope != 'document':
                    raise
                print(f'Document failed: {type(exc).__name__}: {exc}', file=sys.stderr)
            finally:
                record.elapsed_seconds = time.perf_counter() - page_started
            result.elapsed_seconds = time.perf_counter() - started
            _save(output, result)
        succeeded = sum(r.status == 'SUCCEEDED' for r in records)
        result.status = 'COMPLETE' if succeeded == len(records) else 'PARTIAL_FAILED' if succeeded else 'FAILED'
    except KeyboardInterrupt as exc:
        result.status = 'INTERRUPTED'
        result.error = _error(exc, 'interrupted')
    except Exception as exc:
        result.status = 'FAILED'
        result.error = _error(exc, 'batch')
    result.elapsed_seconds = time.perf_counter() - started
    result.finished_at = datetime.now(timezone.utc).isoformat()
    for record in records:
        if record.status == 'RUNNING':
            record.status = 'FAILED'
            record.error = result.error
    _save(output, result)
    return result
