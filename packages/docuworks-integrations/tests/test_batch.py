import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import docuworks_integrations.batch as batch
import docuworks_integrations.recognition as recognition
from docuworks_integrations.results import load_ocr_result, export_jsonl, get_region, sha256
from docuworks_ctypes.errors import XdwError
from docuworks_ctypes._raw import constants as C
from test_multipage import fake, Engine, Renderer


def inputs(tmp_path):
    root = tmp_path / 'input'
    (root / 'nested').mkdir(parents=True)
    for name in ('b.XDW', 'a.xdw', 'nested/a.xdw', 'ignored.txt'):
        (root / name).write_bytes(b'original')
    return root


def test_folder_real_bundles_and_shared_model(fake, tmp_path, monkeypatch, capsys):
    import docuworks_integrations.paddle as paddle
    instances = []
    def factory(root):
        engine = Engine()
        instances.append(engine)
        return engine
    monkeypatch.setattr(paddle, 'PaddleOcrEngine', factory)
    root = inputs(tmp_path)
    before = {str(p): sha256(p) for p in root.rglob('*.xdw')}
    output = tmp_path / 'batch'
    result = batch.ocr_folder(root, output, tmp_path, recursive=True)
    assert result.status == 'COMPLETE' and result.exit_code == 0, result.to_dict()
    assert [d.source_relative_path for d in result.documents] == ['a.xdw', 'b.XDW', 'nested/a.xdw']
    assert len(instances) == 1 and instances[0].calls == [1, 2, 3] * 3
    assert Renderer.instances == 3
    assert len({d.run_id for d in result.documents}) == 3
    for d in result.documents:
        run = load_ocr_result(output / d.run_dir)
        assert run.schema_version == '1.1'
        assert [p.page for p in run.pages] == [1, 2, 3]
        assert [len(p.regions) for p in run.pages] == [1, 0, 1]
        assert get_region(run, 'p0003-r000001').bbox_mm['width'] == 42
        export_jsonl(run, tmp_path / (d.document_id + '.jsonl'))
    assert before == {str(p): sha256(p) for p in root.rglob('*.xdw')}
    assert not capsys.readouterr().out
    assert json.loads((output / 'batch.json').read_text(encoding='utf-8')) == result.to_dict()
    assert not list(output.glob('.batch-*'))
    from jsonschema import Draft202012Validator
    schema = json.loads((Path(batch.__file__).parent / 'ocr-batch-1.0.schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result.to_dict())


def test_shallow_and_snapshot(fake, tmp_path, monkeypatch):
    root = inputs(tmp_path)
    original = batch.ocr_xdw_pages
    def produce(*args, **kwargs):
        (root / 'new.xdw').write_bytes(b'added during batch')
        return original(*args, **kwargs)
    monkeypatch.setattr(batch, 'ocr_xdw_pages', produce)
    result = batch.ocr_folder(root, tmp_path / 'batch', tmp_path, engine=Engine())
    assert [d.source_relative_path for d in result.documents] == ['a.xdw', 'b.XDW']


@pytest.mark.parametrize('kind', ['corrupt', 'missing', 'changed'])
def test_document_failure_continues(fake, tmp_path, monkeypatch, kind):
    root = inputs(tmp_path)
    original = batch.ocr_xdw_pages
    calls = []
    def produce(source, *args, **kwargs):
        calls.append(source.name)
        if source.name == 'a.xdw':
            if kind == 'missing':
                source.unlink()
            elif kind == 'corrupt':
                source.write_bytes(b'bad')
            else:
                from docuworks_integrations.failures import SourceChangedError
                raise SourceChangedError('changed')
        return original(source, *args, **kwargs)
    original_enter = Renderer.__enter__
    def enter(self):
        if self.copy.read_bytes() == b'bad':
            raise XdwError(C.XDW_E_BAD_FORMAT, 'open')
        return original_enter(self)
    monkeypatch.setattr(Renderer, '__enter__', enter)
    monkeypatch.setattr(batch, 'ocr_xdw_pages', produce)
    result = batch.ocr_folder(root, tmp_path / 'batch', tmp_path, engine=Engine())
    assert result.status == 'PARTIAL_FAILED' and result.exit_code == 1
    assert [d.status for d in result.documents] == ['FAILED', 'SUCCEEDED']
    assert calls == ['a.xdw', 'b.XDW']
    assert result.documents[0].error['scope'] == 'document'
    assert not (tmp_path / 'batch/runs/doc-000001/manifest.json').exists()


@pytest.mark.parametrize('kind', ['gpu', 'interrupt', 'internal', 'dll', 'disk', 'missing-model'])
def test_fatal_stops_and_keeps_completed(fake, tmp_path, monkeypatch, kind):
    root = inputs(tmp_path)
    original = batch.ocr_xdw_pages
    def produce(source, *args, **kwargs):
        if source.name == 'b.XDW':
            if kind == 'internal':
                raise KeyError('bug')
            if kind == 'dll':
                raise XdwError(C.XDW_E_NOT_INSTALLED, 'open')
            if kind == 'disk':
                raise OSError(28, 'disk full')
            if kind == 'missing-model':
                def fail(image): raise FileNotFoundError('missing model')
                kwargs['engine'].recognize = fail
            else:
                kwargs['engine'].failure = kind
        return original(source, *args, **kwargs)
    monkeypatch.setattr(batch, 'ocr_xdw_pages', produce)
    result = batch.ocr_folder(root, tmp_path / 'batch', tmp_path, recursive=True, engine=Engine())
    assert result.status == ('INTERRUPTED' if kind == 'interrupt' else 'FAILED')
    assert result.exit_code == (130 if kind == 'interrupt' else 1)
    assert [d.status for d in result.documents] == ['SUCCEEDED', 'FAILED', 'PENDING']
    load_ocr_result(tmp_path / 'batch/runs/doc-000001')
    assert not (tmp_path / 'batch/runs/doc-000002/manifest.json').exists()
    assert not (tmp_path / 'batch/runs/doc-000003').exists()


def test_journal_failure_stops(fake, tmp_path, monkeypatch):
    root = inputs(tmp_path)
    original = batch._save
    writes = []
    def save(output, result):
        writes.append(result.to_dict())
        if len(writes) >= 3:
            raise PermissionError('journal blocked')
        return original(output, result)
    monkeypatch.setattr(batch, '_save', save)
    with pytest.raises(PermissionError):
        batch.ocr_folder(root, tmp_path / 'batch', tmp_path, engine=Engine())
    assert (tmp_path / 'batch/runs/doc-000001/manifest.json').is_file()
    assert not (tmp_path / 'batch/runs/doc-000002').exists()
    assert json.loads((tmp_path / 'batch/batch.json').read_text())['status'] == 'RUNNING'


def test_preflight_no_output_or_engine(tmp_path, monkeypatch):
    root = inputs(tmp_path)
    for output, options in ((root / 'result', {}), (root, {}), (tmp_path / 'bad-dpi', {'dpi': 0})):
        with pytest.raises((ValueError, FileExistsError)):
            batch.ocr_folder(root, output, tmp_path, **options)
    empty = tmp_path / 'empty'
    empty.mkdir()
    with pytest.raises(ValueError, match='No XDW'):
        batch.ocr_folder(empty, tmp_path / 'no-output', tmp_path)
    assert not (tmp_path / 'no-output').exists()
    with pytest.raises(ValueError, match='too long'):
        batch.ocr_folder(root, tmp_path / ('x' * 200), tmp_path)


def test_reparse_excluded_and_rechecked(fake, tmp_path, monkeypatch):
    root = inputs(tmp_path)
    original_linked = batch._linked
    monkeypatch.setattr(batch, '_linked', lambda p: p.name == 'nested' or original_linked(p))
    result = batch.ocr_folder(root, tmp_path / 'batch', tmp_path, recursive=True, engine=Engine())
    assert len(result.documents) == 2
    def switched(source, root):
        raise PermissionError('source became junction')
    monkeypatch.setattr(batch, '_check_source', switched)
    result = batch.ocr_folder(root, tmp_path / 'switched', tmp_path, engine=Engine())
    assert result.status == 'FAILED'
    assert all(d.error['scope'] == 'document' for d in result.documents)
    assert not (tmp_path / 'switched/runs').exists()


def test_cli_and_lightweight_import(fake, tmp_path, monkeypatch, capsys):
    import docuworks_integrations.paddle as paddle
    from docuworks_integrations.cli import main
    monkeypatch.setattr(paddle, 'PaddleOcrEngine', lambda root: Engine())
    root = inputs(tmp_path)
    code = main(['ocr-folder', '--input-dir', str(root), '--batch-dir', str(tmp_path / 'batch'),
                 '--model-root', str(tmp_path)])
    assert code == 0 and json.loads(capsys.readouterr().out)['status'] == 'COMPLETE'
    with pytest.raises(SystemExit) as error:
        main(['ocr-folder', '--input-dir', str(root), '--batch-dir', str(root), '--model-root', str(tmp_path)])
    assert error.value.code == 2
    env = dict(os.environ)
    env['PYTHONPATH'] = str(Path(batch.__file__).resolve().parents[1])
    subprocess.run([sys.executable, '-c',
        "from docuworks_integrations import ocr_folder, OcrBatchResult; import sys; "
        "assert not {'paddle','paddleocr','paddlex','PIL','numpy','cv2','docuworks_ctypes'} & set(sys.modules)"],
        env=env, cwd=tmp_path, check=True)
