import json
from pathlib import Path
import pytest

from docuworks_integrations import _storage as storage
from docuworks_integrations import recognition, results
from test_multipage import fake, Engine


def test_diagnostic_notes_without_add_note():
    class LegacyError(Exception):
        add_note = None
    error = LegacyError('primary')
    storage.note(error, 'first diagnostic')
    storage.note(error, 'second diagnostic')
    assert error.__notes__ == ['first diagnostic', 'second diagnostic']
    assert str(error) == 'primary'


def test_broken_note_does_not_replace_original_error():
    class BrokenError(Exception):
        def add_note(self, message):
            raise RuntimeError('note failed')
    error = BrokenError('primary')
    storage.note(error, 'diagnostic')
    assert str(error) == 'primary'


@pytest.mark.parametrize('directory', [False, True])
def test_publish_refuses_existing_output(tmp_path, directory):
    source, output = tmp_path/'source', tmp_path/'output'
    if directory:
        source.mkdir(); output.mkdir()
        (output/'old').write_bytes(b'old')
    else:
        source.write_bytes(b'new'); output.write_bytes(b'old')
    with pytest.raises(FileExistsError):
        storage.publish_new(source, output)
    assert source.exists()
    assert (output/'old' if directory else output).read_bytes() == b'old'


@pytest.mark.parametrize('error', [ValueError('primary'), KeyboardInterrupt('cancelled')])
def test_cleanup_retains_original_error_and_path(tmp_path, monkeypatch, error):
    def denied(path): raise PermissionError('cleanup denied')
    monkeypatch.setattr(storage.shutil, 'rmtree', denied)
    with pytest.raises(type(error)) as caught:
        with storage.owned_directory(tmp_path, '.test-') as owned:
            (owned/'data').write_bytes(b'diagnostic')
            raise error
    assert caught.value is error
    assert error._ocr_cleanup_failed
    assert any(str(owned) in note for note in error.__notes__)
    assert (owned/'data').read_bytes() == b'diagnostic'


def test_cleanup_failure_without_primary_is_not_success(tmp_path, monkeypatch):
    def denied(path): raise PermissionError('cleanup denied')
    monkeypatch.setattr(storage.shutil, 'rmtree', denied)
    with pytest.raises(PermissionError, match='cleanup denied') as caught:
        with storage.owned_directory(tmp_path, '.test-') as owned:
            pass
    assert any(str(owned) in note for note in caught.value.__notes__)


def test_publish_failure_keeps_diagnostics_without_second_rename(fake, tmp_path, monkeypatch):
    calls = []
    def denied(source, target):
        calls.append((source, target))
        raise PermissionError('publish denied')
    monkeypatch.setattr(Path, 'rename', denied)
    before = results.sha256(fake)
    with pytest.raises(PermissionError, match='publish denied') as caught:
        recognition.ocr_xdw_pages(fake, tmp_path/'failed', tmp_path, engine=Engine())
    assert len(calls) == 1
    error = json.loads((tmp_path/'failed/error.json').read_text(encoding='utf-8'))
    diagnostic = (tmp_path/'failed'/error['diagnostics']).resolve()
    assert diagnostic == calls[0][0]
    assert (diagnostic/'manifest.json').is_file()
    assert (diagnostic/'error.json').is_file()
    with pytest.raises(ValueError, match='unpublished'):
        results.load_ocr_result(diagnostic)
    with pytest.raises(FileNotFoundError):
        results.load_ocr_result(tmp_path/'failed')
    assert results.sha256(fake) == before
    assert str(diagnostic) in '\n'.join(caught.value.__notes__)


def test_diagnostic_write_failure_does_not_mask_ocr_error(fake, tmp_path, monkeypatch):
    original = recognition.write_json
    def write(path, value):
        if path.name == 'error.json': raise PermissionError('diagnostic denied')
        return original(path, value)
    monkeypatch.setattr(recognition, 'write_json', write)
    with pytest.raises(RuntimeError, match='GPU failed') as caught:
        recognition.ocr_xdw_pages(fake, tmp_path/'failed', tmp_path, engine=Engine(failure='gpu'))
    assert caught.value._ocr_failure_scope == 'batch'
    assert any('diagnostic denied' in n for n in caught.value.__notes__)


def test_save_failure_cannot_expose_staging_as_complete(fake, tmp_path, monkeypatch):
    recognition.ocr_xdw_pages(fake, tmp_path/'run', tmp_path, engine=Engine())
    result = results.load_ocr_result(tmp_path/'run')
    before = results.sha256(tmp_path/'run/manifest.json')
    def denied(*args): raise PermissionError('publish denied')
    with monkeypatch.context() as patch:
        patch.setattr(results, 'publish_new', denied)
        patch.setattr(storage.shutil, 'rmtree', denied)
        with pytest.raises(PermissionError, match='publish denied') as caught:
            results.save_ocr_result(result, tmp_path/'copy')
    staging, = tmp_path.glob('.ocr-*')
    assert (staging/'manifest.json').exists()
    assert not (tmp_path/'copy').exists()
    with pytest.raises(ValueError, match='unpublished'):
        results.load_ocr_result(staging)
    assert caught.value._ocr_cleanup_failed
    assert results.sha256(tmp_path/'run/manifest.json') == before


def test_unchanged_journal_does_not_replace_and_failed_update_retains_old(tmp_path, monkeypatch):
    storage.atomic_json(tmp_path, {'status': 'RUNNING'})
    old = (tmp_path/'job.json').read_bytes()
    calls = []
    def denied(*args):
        calls.append(args)
        raise PermissionError('replace denied')
    monkeypatch.setattr(storage.os, 'replace', denied)
    storage.atomic_json(tmp_path, {'status': 'RUNNING'})
    assert calls == []
    with pytest.raises(PermissionError, match='replace denied'):
        storage.atomic_json(tmp_path, {'status': 'COMPLETE'})
    assert len(calls) == 1
    assert (tmp_path/'job.json').read_bytes() == old
    assert not list(tmp_path.glob('.job-*'))


def test_preflight_cleanup_failure_stops_before_ocr(fake, tmp_path, monkeypatch):
    from docuworks_integrations import jobs
    monkeypatch.setattr(jobs, 'resolve_font', lambda *a: None)
    original = Path.rmdir
    def denied(path):
        if path.name.startswith('.write-probe-'): raise PermissionError('probe cleanup denied')
        return original(path)
    monkeypatch.setattr(Path, 'rmdir', denied)
    engine = Engine()
    result = jobs.process_documents([fake], tmp_path/'out', tmp_path/'runs', tmp_path, engine=engine)
    assert result['status'] == 'FAILED' and not engine.calls
    assert result['documents'][0]['ocr'] == 'PENDING'
    assert any('.write-probe-' in n for n in result['error']['notes'])


def test_file_cleanup_refuses_directory(tmp_path):
    directory = tmp_path/'not-a-file'
    directory.mkdir()
    with pytest.raises(OSError):
        storage.cleanup_owned(directory)
    assert directory.is_dir()


def test_job_journal_error_does_not_mask_gpu_failure(fake, tmp_path, monkeypatch):
    from docuworks_integrations import jobs
    monkeypatch.setattr(jobs, 'resolve_font', lambda *a: None)
    original = jobs._journal
    def journal(folder, payload):
        if payload['documents'][0]['ocr'] == 'FAILED':
            raise PermissionError('journal denied')
        return original(folder, payload)
    monkeypatch.setattr(jobs, '_journal', journal)
    with pytest.raises(RuntimeError, match='GPU failed') as caught:
        jobs.process_documents([fake], tmp_path/'out', tmp_path/'runs', tmp_path,
                               engine=Engine(failure='gpu'))
    assert any('journal denied' in n for n in caught.value.__notes__)
    old = json.loads((tmp_path/'out/job.json').read_text(encoding='utf-8'))
    assert old['status'] == 'RUNNING'  # Failed final save must not claim completion.
    assert not (tmp_path/'runs/doc-000001/manifest.json').exists()


def test_publish_refuses_destination_created_during_verification(fake, tmp_path, monkeypatch):
    original = recognition.publish_new
    def collision(source, target):
        target.mkdir()
        (target/'foreign.txt').write_bytes(b'keep')
        return original(source, target)
    monkeypatch.setattr(recognition, 'publish_new', collision)
    with pytest.raises(FileExistsError):
        recognition.ocr_xdw_pages(fake, tmp_path/'run', tmp_path, engine=Engine())
    assert list((tmp_path/'run').iterdir()) == [tmp_path/'run/foreign.txt']
    assert (tmp_path/'run/foreign.txt').read_bytes() == b'keep'
