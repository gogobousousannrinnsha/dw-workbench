"""Validate an installed wheel and an unmodified sdist in an independent environment."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile

from publication_policy import content_error, path_error, MAX_ARCHIVE_BYTES, MAX_FILE_BYTES


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def verify(archive, tests, output, dll=None, *, expected_version):
    archive, tests, output = map(lambda p: Path(p).resolve(), (archive, tests, output))
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    env.pop('DOCUWORKS_REVIEWED_DLL', None)
    if dll: env['DOCUWORKS_REVIEWED_DLL'] = str(dll)
    results = {}
    for kind in ('wheel', 'sdist'):
        run = output / kind
        run.mkdir()
        if kind == 'sdist':
            unpacked = run / 'source'; unpacked.mkdir()
            seen, total = set(), 0
            with tarfile.open(archive, 'r:gz') as handle:
                for member in handle:
                    if member.isdir(): continue
                    total += member.size
                    if (not member.isfile() or member.name in seen or path_error(member.name)
                            or member.size > MAX_FILE_BYTES or total > MAX_ARCHIVE_BYTES):
                        raise ValueError('unsafe sdist member')
                    seen.add(member.name)
                    with handle.extractfile(member) as stream: data = stream.read()
                    if content_error(data): raise ValueError('non-distributable member')
                    dest = unpacked / member.name
                    dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(data)
            source = unpacked / archive.name.removesuffix('.tar.gz')
            for document in source.rglob('*.md'):
                for target in re.findall(r'\]\(([^)]+)\)', document.read_text(encoding='utf-8-sig')):
                    if target.startswith(('https://', 'http://', '#', 'mailto:')): continue
                    if not (document.parent / target.split('#')[0]).exists():
                        raise ValueError('broken sdist document link: ' + target)
            before = hashes(unpacked)
            test_dir = source / 'tests'
            env['PYTHONPATH'] = os.pathsep.join((str(source), str(test_dir)))
            expected_import = source
        else:
            test_dir = tests
            env['PYTHONPATH'] = str(tests)
            expected_import = Path(sys.prefix).resolve()
        probe = ('import docuworks_integrations as p; from pathlib import Path; import sys; '
                 'assert p.__version__==sys.argv[2]; '
                 'assert Path(p.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve()); '
                 'print(p.__file__)')
        loaded = subprocess.check_output([sys.executable, '-B', '-c', probe, str(expected_import), expected_version], cwd=run, env=env, text=True).strip()
        env['DOCUWORKS_INTEGRATIONS_TEST_TMP'] = str(run / 'temp')
        with (run / 'pytest.log').open('wb') as log:
            process = subprocess.run([sys.executable, '-B', '-m', 'pytest', str(test_dir), '-p', 'no:cacheprovider',
                                      '--junitxml=' + str(run / 'junit.xml')], cwd=run, env=env, stdout=log, stderr=subprocess.STDOUT)
        # Existing subprocess tests deliberately use isolated Python mode; that
        # mode ignores PYTHONDONTWRITEBYTECODE and may create import caches.
        added = set()
        unchanged = True
        if kind == 'sdist':
            after = hashes(unpacked)
            added = set(after) - set(before)
            unchanged = (all(after.get(k) == v for k, v in before.items()) and
                         all('__pycache__' in Path(k).parts and k.endswith('.pyc') for k in added))
        results[kind] = dict(exit_code=process.returncode, source_unchanged=unchanged,
                             import_path=loaded, supplemental_source_files_added=False,
                             generated_cache_files=len(added))
        (output / 'verification.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
        if process.returncode or not unchanged: raise RuntimeError(kind + ' validation failed')
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sdist'); parser.add_argument('tests'); parser.add_argument('output'); parser.add_argument('--dll')
    parser.add_argument('--expected-version', required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.sdist, args.tests, args.output, args.dll, expected_version=args.expected_version), indent=2))
