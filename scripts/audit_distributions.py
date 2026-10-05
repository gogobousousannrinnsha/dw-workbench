"""Audit actual wheel/sdist contents without extracting or disclosing their data."""
from __future__ import annotations
import argparse
from pathlib import Path
import stat
import tarfile
import zipfile
from publication_policy import MAX_ARCHIVE_BYTES, MAX_FILE_BYTES, content_error, path_error

EXPECTED_PACKAGES = {'docuworks_ctypes', 'docuworks_integrations'}


def members(archive):
    if archive.suffix == '.whl':
        with zipfile.ZipFile(archive) as handle:
            for member in handle.infolist():
                if member.is_dir():
                    continue
                special = stat.S_ISLNK(member.external_attr >> 16)
                yield member.filename, member.file_size, special, lambda m=member: handle.open(m)
    else:
        with tarfile.open(archive, 'r:gz') as handle:
            for member in handle:
                if member.isdir():
                    continue
                yield member.name, member.size, not member.isfile(), lambda m=member: handle.extractfile(m)


def audit(dist_dir: Path) -> None:
    problems = []
    archives = sorted(p for p in dist_dir.iterdir() if p.is_file())
    expected = {(package, kind): 0 for package in EXPECTED_PACKAGES for kind in ('wheel', 'sdist')}
    for archive in archives:
        kind = 'wheel' if archive.suffix == '.whl' else 'sdist' if archive.name.endswith('.tar.gz') else None
        package = archive.name.split('-', 1)[0]
        if (package, kind) not in expected:
            problems.append(f'{archive.name}: unexpected distribution'); continue
        expected[package, kind] += 1
        seen = set()
        total = 0
        try:
            for index, (name, size, special, open_member) in enumerate(members(archive), 1):
                total += size
                if total > MAX_ARCHIVE_BYTES or index > 5000:
                    problems.append(f'{archive.name}: archive size/member limit exceeded'); break
                error = 'link or special member' if special else path_error(name)
                if name in seen:
                    error = 'duplicate member'
                seen.add(name)
                if size > MAX_FILE_BYTES:
                    error = 'file exceeds size limit'
                if error is None:
                    with open_member() as stream:
                        error = content_error(stream.read(MAX_FILE_BYTES + 1))
                if error:
                    # Member paths can themselves contain private information.
                    problems.append(f'{archive.name}: member #{index}: {error}')
        except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile, RuntimeError) as exc:
            problems.append(f'{archive.name}: unreadable archive ({type(exc).__name__})')
        if package == 'docuworks_integrations' and kind == 'sdist':
            prefix = archive.name.removesuffix('.tar.gz')
            if prefix + '/tests/conftest.py' not in seen:
                problems.append(f'{archive.name}: missing tests/conftest.py')
    for (package, kind), count in sorted(expected.items()):
        if count != 1:
            problems.append(f'expected exactly one {kind} for {package}, found {count}')
    if problems:
        raise SystemExit('distribution audit failed:\n' + '\n'.join(problems))
    print('distribution audit passed: four archives; text-only content and private-data checks passed.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('dist_dir', nargs='?', default='dist', type=Path)
    audit(parser.parse_args().dist_dir)


if __name__ == '__main__':
    main()
