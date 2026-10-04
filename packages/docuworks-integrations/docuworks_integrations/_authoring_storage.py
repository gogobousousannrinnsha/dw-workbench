"""Small, process-safe storage helpers for mutable authoring workspaces."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import uuid

from . import reviewed as r


@contextmanager
def locked(folder):
    """An OS-owned lock is released even when an editor/worker crashes."""
    path = r._plain_path(Path(folder) / '.authoring.lock')
    with path.open('a+b') as stream:
        if stream.seek(0, 2) == 0:
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('別の画面・処理で使用中です。処理を終えてから再操作してください。') from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def atomic_write(path, data):
    path = r._plain_path(path)
    temporary = path.with_name('.authoring-' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(r._bytes(data)); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read(path):
    return json.loads(r._plain_path(path).read_text(encoding='utf-8'))


def copy_reviewed(source, destination):
    source = r.load_reviewed_result(source).root
    manifest = read(source / 'manifest.json')
    destination.mkdir()
    for name in [*manifest['files'], 'manifest.json']:
        r._copy(source / name, destination / name)
    original = r.load_reviewed_result(source)
    copied = r.load_reviewed_result(destination)
    if original.manifest_sha256 != copied.manifest_sha256:
        raise RuntimeError('見本がコピー中に変更されました。')
    return copied
