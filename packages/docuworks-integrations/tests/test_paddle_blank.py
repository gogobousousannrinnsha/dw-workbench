"""Synthetic regression cases: no Paddle, GPU or DocuWorks DLL needed."""
from copy import deepcopy
import json
import logging
from pathlib import Path

import pytest

from docuworks_integrations.paddle import parse_paddle_result
from docuworks_integrations import OcrRegion, PixelRect
from docuworks_integrations.results import load_ocr_result, export_jsonl, sha256
from docuworks_integrations.recognition import ocr_xdw_pages
from test_multipage import fake


def payload():
    rows = json.loads((Path(__file__).parent / 'fixtures/paddle-blank.json').read_text(encoding='utf-8'))['rows']
    return dict(rec_texts=[r[0] for r in rows], rec_scores=[r[1] for r in rows], rec_polys=[r[2] for r in rows])


@pytest.mark.parametrize('blank', ['', ' ', '\t', '\n', '\r\n', '\u3000', ' \t\n\u3000'])
@pytest.mark.parametrize('wrapped', [False, True])
def test_blank_skipped_without_changing_input_or_survivors(blank, wrapped, caplog):
    data = payload()
    data['rec_texts'][1] = blank
    control = deepcopy(data)
    control['rec_texts'][1] = 'CONTROL'
    expected = parse_paddle_result(control, 200, 200)
    original = deepcopy(data)
    with caplog.at_level(logging.WARNING, logger='docuworks_integrations.paddle'):
        result = parse_paddle_result({'res': data} if wrapped else data, 200, 200)
    assert result == (expected[0], expected[2])
    assert data == original
    messages = [r.getMessage() for r in caplog.records if r.name == 'docuworks_integrations.paddle']
    assert messages == ['Skipped 1 blank OCR text region(s)']
    assert 'ABC' not in messages[0] and 'DEF' not in messages[0]


def test_normal_text_exact_and_no_skip_log(caplog):
    data = payload()
    data['rec_texts'] = [' 日本語 "引用"\n次行\t ', 'ABC', 'DEF']
    result = parse_paddle_result(data, 200, 200)
    assert [r.text for r in result] == data['rec_texts']
    assert not caplog.records


@pytest.mark.parametrize('count', [0, 3])
def test_no_usable_text(count, caplog):
    data = payload()
    data['rec_texts'] = [''] * count
    for key in ('rec_scores', 'rec_polys'):
        data[key] = data[key][:count]
    assert parse_paddle_result(data, 200, 200) == ()
    assert [r.getMessage() for r in caplog.records] == (
        ['Skipped 3 blank OCR text region(s)'] if count else [])


@pytest.mark.parametrize('kind', ['nonstring', 'length', 'nan', 'infinity', 'negative',
                                  'over_one', 'bad_score', 'outside', 'area', 'shape', 'point_nan'])
def test_invalid_blank_row_still_rejected(kind, caplog):
    data = payload()
    if kind == 'nonstring': data['rec_texts'][1] = None
    if kind == 'length': data['rec_scores'].pop()
    if kind == 'nan': data['rec_scores'][1] = float('nan')
    if kind == 'infinity': data['rec_scores'][1] = float('inf')
    if kind == 'negative': data['rec_scores'][1] = -.1
    if kind == 'over_one': data['rec_scores'][1] = 1.1
    if kind == 'bad_score': data['rec_scores'][1] = 'invalid'
    if kind == 'outside': data['rec_polys'][1][0][0] = -1
    if kind == 'area': data['rec_polys'][1] = [[10, 10]] * 4
    if kind == 'shape': data['rec_polys'][1].pop()
    if kind == 'point_nan': data['rec_polys'][1][0][0] = float('nan')
    with pytest.raises(ValueError):
        parse_paddle_result(data, 200, 200)
    assert not caplog.records  # No successful-skip message for a rejected page.


@pytest.mark.parametrize('text', ['', ' \t\n\u3000', None])
def test_region_contract_unchanged(text):
    with pytest.raises(ValueError, match='non-empty string'):
        OcrRegion(text, PixelRect(1, 1, 3, 4), .9)


class Engine:
    def __init__(self, mode='mixed'):
        self.mode = mode
        self.calls = []
        self.last_raw = None

    def recognize(self, image):
        page = int(image.parent.name.split('-')[1])
        self.calls.append(page)
        data = payload()
        if self.mode == 'empty':
            data['rec_texts'] = ['', ' \n', '\u3000']
        elif self.mode == 'zero':
            data = {k: [] for k in data}
        elif page != 2:
            data['rec_texts'][1] = 'CONTROL'
        elif self.mode == 'invalid':
            data['rec_scores'][1] = float('nan')
        elif self.mode == 'invalid_text':
            data['rec_texts'][1] = None
        elif self.mode == 'invalid_geometry':
            data['rec_polys'][1][0][0] = -1
        self.last_raw = deepcopy(data)
        result = parse_paddle_result(data, 1000, 1000)
        assert data == self.last_raw
        return result


def tree_hashes(root):
    return {p.relative_to(root).as_posix(): sha256(p) for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('mode', ['mixed', 'empty', 'zero'])
def test_complete_pages_saved_raw_and_jsonl(fake, tmp_path, mode):
    engine = Engine(mode)
    source_hash = sha256(fake)
    run = tmp_path / 'run'
    ocr_xdw_pages(fake, run, tmp_path, engine=engine)
    before = tree_hashes(run)
    result = load_ocr_result(run)
    expected_counts = [3, 2, 3] if mode == 'mixed' else [0, 0, 0]
    assert [len(p.regions) for p in result.pages] == expected_counts
    assert engine.calls == [1, 2, 3]
    for page in result.pages:
        assert page.recognition_status == ('TEXT_DETECTED' if page.regions else 'NO_TEXT_DETECTED')
    output = tmp_path / 'regions.jsonl'
    export_jsonl(result, output)
    rows = [json.loads(line) for line in output.read_text(encoding='utf-8').splitlines()]
    assert len(rows) == sum(expected_counts)
    if mode == 'mixed':
        assert [r.text for r in result.pages[1].regions] == ['ABC', 'DEF']
        assert json.loads((run / 'pages/page-0002/raw-paddle.json').read_text()) == payload()
        assert [r.id for r in result.pages[1].regions] == ['p0002-r000001', 'p0002-r000002']
        assert result.pages[1].regions[1].confidence == .7
        assert result.pages[1].regions[1].bbox_px == {'x': 80., 'y': 50., 'width': 60., 'height': 20.}
    else:
        assert output.read_bytes() == b''
    with pytest.raises(FileExistsError):
        ocr_xdw_pages(fake, run, tmp_path, engine=Engine(mode))
    ocr_xdw_pages(fake, tmp_path / 'second-run', tmp_path, engine=Engine(mode))
    assert tree_hashes(run) == before and sha256(fake) == source_hash


@pytest.mark.parametrize('mode', ['mixed', 'empty', 'zero', 'invalid', 'invalid_text', 'invalid_geometry'])
def test_batch_continuation_and_invalid_still_stop(fake, tmp_path, monkeypatch, mode):
    from docuworks_integrations import jobs
    from docuworks_integrations.settings import Settings
    monkeypatch.setattr(jobs, 'resolve_font', lambda *a: None)
    monkeypatch.setattr(jobs, 'annotate_rectangles', lambda *a, **k: None)
    monkeypatch.setattr(jobs, 'render_text_maps', lambda *a, **k: None)
    other = tmp_path / 'z-other.xdw'
    other.write_bytes(fake.read_bytes())
    engine = Engine(mode)
    job = jobs.process_documents([fake, other], tmp_path / 'out', tmp_path / 'runs', tmp_path,
                                engine=engine, settings=Settings(jsonl=True))
    if mode.startswith('invalid'):
        assert job['status'] == 'FAILED' and job['exit_code'] == 1
        assert [d['ocr'] for d in job['documents']] == ['FAILED', 'PENDING']
        run = tmp_path / 'runs/doc-000001'
        assert not (run / 'manifest.json').exists()
        error = json.loads((run / 'error.json').read_text())
        assert error['phase'] == 'recognize' and error['failure_scope'] == 'batch'
        assert error['failed_page'] == 2 and error['completed_pages'] == [1]
        assert ((run / error['diagnostics']).resolve() / 'pages/page-0002/raw-paddle.json').is_file()
        assert engine.calls == [1, 2]
    else:
        assert job['status'] == 'COMPLETE' and job['exit_code'] == 0
        assert engine.calls == [1, 2, 3, 1, 2, 3]
        assert all(d['ocr'] == d['jsonl'] == 'SUCCEEDED' for d in job['documents'])
