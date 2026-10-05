"""Replay synthetic Paddle output before/after the fix without Paddle or an SDK.

Use --expect before on 8f8d537 and --expect after on the fixed source.
Only the renderer and native rectangle output are replaced; parsing, recognition,
failure classification, bundle publication, text maps and JSONL remain real.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import platform
import subprocess
import sys
from unittest.mock import patch

from docuworks_integrations import jobs, recognition, derivatives
from docuworks_integrations.paddle import parse_paddle_result
from docuworks_integrations.results import load_ocr_result, export_jsonl
from docuworks_integrations.settings import Settings
import docuworks_integrations.paddle as paddle_adapter


class Renderer:
    page_count = 3
    dll_path = None

    def __init__(self, source, dll_path):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def render(self, page, folder, dpi):
        from PIL import Image
        Image.new('RGB', (200, 200), 'white').save(folder / 'image.png')
        return dict(page_width_mm=100, page_height_mm=100,
                    image_width_px=200, image_height_px=200)


class ReplayEngine:
    def __init__(self, payload):
        self.payload = payload
        self.last_raw = None
        self.calls = []

    def recognize(self, image):
        page = int(image.parent.name.split('-')[1])
        self.calls.append(page)
        self.last_raw = deepcopy(self.payload)
        if page != 2:
            self.last_raw['rec_texts'][1] = 'CONTROL'
        return parse_paddle_result(self.last_raw, 200, 200)


def failed_run(run, expected_payload):
    assert not (run / 'manifest.json').exists()
    error = json.loads((run / 'error.json').read_text(encoding='utf-8'))
    assert (error['type'], error['phase'], error['failure_scope']) == ('ValueError', 'recognize', 'batch')
    assert error['failed_page'] == 2 and error['completed_pages'] == [1]
    assert error['message'] == 'OCR text must be a non-empty string'
    diagnostic = (run / error['diagnostics']).resolve()
    assert not (diagnostic / 'manifest.json').exists()
    raw = json.loads((diagnostic / 'pages/page-0002/raw-paddle.json').read_text(encoding='utf-8'))
    assert raw == expected_payload
    assert (diagnostic / 'pages/page-0001/result.json').is_file()
    return {key: error[key] for key in ('type', 'message', 'phase', 'failure_scope', 'failed_page', 'completed_pages')}


def replay(fixture, output, expect):
    output.mkdir(parents=True, exist_ok=False)
    original = fixture.read_bytes()
    rows = json.loads(original)['rows']
    payload = dict(rec_texts=[r[0] for r in rows], rec_scores=[r[1] for r in rows], rec_polys=[r[2] for r in rows])
    (output / 'input.json').write_bytes(original)
    report = dict(expected=expect, python=platform.python_version(),
                  input_sha256=sha256(original).hexdigest(),
                  payload_sha256=sha256(json.dumps(payload, sort_keys=True).encode('utf-8')).hexdigest(),
                  baseline='8f8d53765b4ba237268aa942fef32353f90fa7c9',
                  checkout_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                  parser_sha256=sha256(Path(paddle_adapter.__file__).read_bytes()).hexdigest(),
                  replay_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                  tracked_changes_present=bool(subprocess.check_output(['git', 'diff', '--name-only'], text=True).strip()),
                  minimal=[], actual_user_document_tested=False)
    for text in ('', ' ', '\t', '\n', '\u3000', None, 'CONTROL'):
        data = deepcopy(payload)
        data['rec_texts'][1] = text
        snapshot = deepcopy(data)
        try:
            regions = parse_paddle_result(data, 200, 200)
        except ValueError as exc:
            assert text is None or (expect == 'before' and text != 'CONTROL')
            assert str(exc) == 'OCR text must be a non-empty string'
            report['minimal'].append(dict(text=text, error=str(exc)))
        else:
            assert text == 'CONTROL' or (expect == 'after' and text is not None)
            expected = ['ABC', 'CONTROL', 'DEF'] if text == 'CONTROL' else ['ABC', 'DEF']
            assert [r.text for r in regions] == expected
            report['minimal'].append(dict(text=text, output=expected))
        assert data == snapshot
    source = output / 'source.xdw'
    source.write_bytes(b'synthetic renderer input, not a real XDW')
    source_hash = sha256(source.read_bytes()).hexdigest()
    engine = ReplayEngine(payload)
    with patch.object(recognition, 'XdwRenderer', Renderer):
        try:
            recognition.ocr_xdw_pages(source, output / 'run', output, engine=engine)
        except ValueError:
            assert expect == 'before'
            report['document'] = failed_run(output / 'run', payload)
            assert engine.calls == [1, 2]
        else:
            assert expect == 'after'
            result = load_ocr_result(output / 'run')
            assert [len(p.regions) for p in result.pages] == [3, 2, 3]
            export_jsonl(result, output / 'regions.jsonl')
            assert engine.calls == [1, 2, 3]
            report['document'] = dict(status='COMPLETE', regions=[3, 2, 3])
        inputs = output / 'input'
        inputs.mkdir()
        for name in ('a.xdw', 'b.xdw'):
            (inputs / name).write_bytes(source.read_bytes())
        # Real rectangle planning only; never claim this creates/reopens an XDW.
        def rectangles(*args, **kwargs):
            return derivatives.annotate_rectangles(*args, **kwargs, dry_run=True)
        batch_engine = ReplayEngine(payload)
        with patch.object(jobs, 'annotate_rectangles', rectangles):
            job = jobs.process_documents([inputs], output / 'job', output / 'runs', output,
                                         engine=batch_engine, settings=Settings(jsonl=True))
        report['batch'] = dict(status=job['status'], exit_code=job['exit_code'],
                               ocr=[d['ocr'] for d in job['documents']], calls=batch_engine.calls,
                               native_rectangles='dry-run only')
        if expect == 'before':
            assert job['status'] == 'FAILED' and job['exit_code'] == 1
            assert report['batch']['ocr'] == ['FAILED', 'PENDING']
            assert batch_engine.calls == [1, 2]
            failed_run(output / 'runs/doc-000001', payload)
        else:
            assert job['status'] == 'COMPLETE' and job['exit_code'] == 0
            assert batch_engine.calls == [1, 2, 3, 1, 2, 3]
            assert all(d[s] == 'SUCCEEDED' for d in job['documents']
                       for s in ('ocr', 'rectangles', 'text_maps', 'jsonl'))
    assert sha256(source.read_bytes()).hexdigest() == source_hash
    assert fixture.read_bytes() == original
    assert not any(name in sys.modules for name in ('paddle', 'paddleocr'))
    report['status'] = 'PASS'
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect', choices=('before', 'after'), required=True)
    args = parser.parse_args()
    replay(args.fixture.resolve(), args.output.resolve(), args.expect)
