"""Internal publication and cleanup primitives; no OCR or native dependencies.

Callers own every temporary path passed to cleanup_owned. Published destinations
are never cleaned up here. Windows rename preserves the no-overwrite contract.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import sys
import uuid


def note(error, message):
    # Keep diagnostic paths available to JSON reports on Python 3.10 too.
    # Diagnostics must never replace the failure they describe.
    try:
        add_note = getattr(error, 'add_note', None)
        if callable(add_note):
            add_note(message)
        else:
            error.__notes__ = [*getattr(error, '__notes__', []), message]
    except Exception:
        pass


def require_public_result(path):
    # A failed publish can leave a valid manifest in private staging. Never let
    # consumers treat that directory as a published bundle, even if cleanup failed.
    if re.fullmatch(r'\.(?:recognition-[0-9a-f]{12}|ocr-[0-9a-f]{32})', Path(path).name):
        raise ValueError('unpublished OCR staging directory')


def publish_new(source, destination):
    """Atomically rename an already-verified artifact, refusing existing output."""
    source, destination = Path(source), Path(destination)
    if os.path.lexists(destination):
        raise FileExistsError(destination)
    try:
        source.rename(destination)
    except OSError as exc:
        note(exc, f'Publication rename failed: {source} -> {destination}; output is not confirmed.')
        raise


def cleanup_owned(path, *, tree=False, directory=False, primary=None):
    """Remove only a caller-created temporary path; retain the primary error."""
    path = Path(path)
    try:
        if not os.path.lexists(path):
            return
        if tree:
            if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
                raise OSError('refusing recursive cleanup of a linked directory')
            shutil.rmtree(path)
        elif directory:
            path.rmdir()
        else:
            path.unlink()
    except OSError as exc:
        message = f'Temporary cleanup failed; retained path: {path}: {exc}'
        if primary is None:
            note(exc, message)
            raise
        primary._ocr_cleanup_failed = True
        note(primary, message)


@contextmanager
def owned_directory(parent, prefix):
    path = Path(parent) / (prefix + uuid.uuid4().hex)
    path.mkdir()
    try:
        yield path
    finally:
        cleanup_owned(path, tree=True, primary=sys.exc_info()[1])


def check_publish_access(folder):
    probe = Path(folder) / ('.write-probe-' + uuid.uuid4().hex)
    renamed = Path(folder) / ('.write-probe-' + uuid.uuid4().hex)
    probe.mkdir()
    try:
        publish_new(probe, renamed)
    except OSError as exc:
        raise OSError(f'Cannot finalize folders in {folder}; no OCR was started: {exc}') from exc
    finally:
        primary = sys.exc_info()[1]
        # Only one of these paths is owned: rename either succeeded or failed.
        cleanup_owned(renamed if not os.path.lexists(probe) else probe, directory=True, primary=primary)


def atomic_json(folder, payload):
    """Skip byte-identical journals; otherwise fsync and atomically replace."""
    folder = Path(folder)
    destination = folder / 'job.json'
    data = (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    try:
        if destination.read_bytes() == data:
            return
    except FileNotFoundError:
        pass
    path = folder / ('.job-' + uuid.uuid4().hex + '.tmp')
    created = False
    try:
        with path.open('xb') as stream:
            created = True
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(path, destination)
    except OSError as exc:
        note(exc, f'Job journal replace failed: {destination}')
        raise
    finally:
        if created:
            cleanup_owned(path, primary=sys.exc_info()[1])
