"""Isolated A/B Portable entry. Both choices perform a fresh, complete OCR job."""
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import uuid


class Tee:
    def __init__(self, console, log): self.console, self.log = console, log
    def write(self, value):
        self.console.write(value); self.log.write(value); self.log.flush()
        return len(value)
    def flush(self): self.console.flush(); self.log.flush()


def tree_hash(root):
    digest = hashlib.sha256()
    for path in sorted(Path(root).rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts:
            continue
        digest.update(path.relative_to(root).as_posix().encode('utf-8')+b'\0')
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024*1024), b''): digest.update(block)
    return digest.hexdigest()


def ocr_summary(run):
    # Exclude fresh UUIDs and timestamps; retain content, geometry and item order.
    pages = [dict(page=p.page, width=p.page_width_mm, height=p.page_height_mm,
                  items=[dict(id=r.id, text=r.text, bbox=r.bbox_mm, polygon=r.polygon_mm)
                         for r in p.regions]) for p in run.pages]
    encoded = json.dumps(pages, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return dict(pages=len(pages), items=sum(len(p['items']) for p in pages),
                content_geometry_sha256=hashlib.sha256(encoded).hexdigest())


def execute(root, variant, arguments):
    from dataclasses import replace
    import docuworks_ctypes
    import docuworks_integrations
    from docuworks_integrations._authoring_storage import locked
    from docuworks_integrations._performance import Recorder, measure
    from docuworks_integrations.jobs import process_documents
    from docuworks_integrations.results import load_ocr_result
    from docuworks_integrations.settings import load_settings
    mode = {'A': 'document', 'B': 'page_join'}[variant]
    job_name = 'job-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
    output = root/'OUTPUT'/variant/job_name
    runs = root/'runs'/variant/job_name
    logs = root/'logs'; logs.mkdir(exist_ok=True)
    result = dict(status='FAILED', exit_code=1, documents=[])
    error = None
    # This OS lock is released on exceptions and process exit, including a crash.
    with locked(root), (logs/(job_name+'.log')).open('x', encoding='utf-8') as log:
        with redirect_stdout(Tee(sys.stdout, log)), redirect_stderr(Tee(sys.stderr, log)):
            recorder = Recorder(variant=variant, review_creation_mode=mode, job=job_name,
                                python=sys.version, started_at=datetime.now().astimezone().isoformat())
            with recorder:
                try:
                    with measure('preflight'):
                        settings = load_settings(root/'settings.ini')
                        if settings.font:
                            settings = replace(settings, font=str((root/settings.font).resolve()))
                        from docuworks_ctypes import XdwApi
                        runtime = XdwApi.load().runtime_info
                        recorder.metadata.update(settings=settings.to_dict(), fingerprints=dict(
                            models=tree_hash(root/'models'),
                            core=tree_hash(Path(docuworks_ctypes.__file__).parent),
                            integrations=tree_hash(Path(docuworks_integrations.__file__).parent),
                            sdk_version=runtime.version_text, dll_sha256=runtime.dll_sha256,
                            dependencies={name:importlib.metadata.version(name) for name in
                                          ('paddleocr', 'paddlex', 'paddlepaddle-gpu', 'Pillow')}))
                    print(f'検証版 {variant}: {mode} / 元のXDWからOCRを開始します。', flush=True)
                    result = process_documents(arguments or [root/'INPUT'], output, runs,
                        root/'models', settings=settings, review=True, review_creation_mode=mode,
                        excluded=[root/p for p in ('OUTPUT', 'runs', 'logs', 'cache', 'ocr-cache',
                                                  'runtime', 'models', 'reference')])
                    with measure('postflight'):
                        documents = []
                        for record in result['documents']:
                            item = dict(document_id=record['document_id'], source_name=record['source_name'],
                                        source_sha256=record.get('source_sha256'),
                                        ocr_status=record['ocr'], review_status=record['review'])
                            if record['ocr'] == 'SUCCEEDED':
                                item.update(ocr_summary(load_ocr_result(output/record['run_dir'])))
                            if record['review'] == 'SUCCEEDED':
                                path = output/record['review_dir']/'review.xdw'
                                item['review_xdw_bytes'] = path.stat().st_size
                                print('校正する文書: '+str(path), flush=True)
                            documents.append(item)
                        recorder.metadata['documents'] = documents
                except (Exception, KeyboardInterrupt) as exc:
                    error = dict(type=type(exc).__name__, message=str(exc), notes=getattr(exc, '__notes__', []))
                    result.update(status='INTERRUPTED' if isinstance(exc, KeyboardInterrupt) else 'FAILED',
                                  exit_code=130 if isinstance(exc, KeyboardInterrupt) else 1)
                    print(f'{type(exc).__name__}: {exc}', file=sys.stderr, flush=True)
            path = recorder.write(output, status=result['status'], exit_code=result['exit_code'], error=error)
            print('処理結果: '+result['status'])
            print('計測結果: '+str(path))
            print('ログ: '+str(logs/(job_name+'.log')))
    return result['exit_code']


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in ('A', 'B'):
        raise ValueError('A または B と、必要に応じて入力XDW／フォルダーを指定してください。')
    root = Path(__file__).resolve().parents[1]
    os.environ['DW_OCR_CACHE'] = str(root/'cache')
    os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
    return execute(root, args.pop(0), args)


if __name__ == '__main__':
    try: code = main()
    except (KeyboardInterrupt, EOFError): code = 130
    except Exception as exc: code = 1; print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
    raise SystemExit(code)
