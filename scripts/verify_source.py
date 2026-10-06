"""Verify fixed implementation hashes and publication boundaries without imports."""
from pathlib import Path
import hashlib
import json
import re
import sys
import io
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / 'SOURCE_SNAPSHOT.json').read_text(encoding='utf-8'))
errors = []
expected = {item['path']: item for item in MANIFEST['implementation_files']}
for relative, item in expected.items():
    path = ROOT / relative
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
        errors.append(f'Implementation hash mismatch: {relative}')
for component in MANIFEST['components']:
    module = ROOT / component['path'] / component['module']
    for path in module.rglob('*.py'):
        if '__pycache__' not in path.parts and path.relative_to(ROOT).as_posix() not in expected:
            errors.append(f'Unexpected implementation file: {path.relative_to(ROOT)}')

# These are private-machine paths; legitimate Windows system paths and synthetic
# drive-relative traversal fixtures are intentionally allowed.
private_path = re.compile(r'(?i)(?:[A-Z]:[\\/]+Users[\\/]+|[A-Z]:[\\/]+ai[\\/]+)')
text_extensions = {'.py', '.ps1', '.bat', '.cmd', '.json', '.md', '.toml', '.yml', '.yaml', '.txt', '.html'}
for path in ROOT.rglob('*'):
    relative = path.relative_to(ROOT)
    if not path.is_file() or any(part in {'.git', '.venv', 'build', 'dist', '__pycache__', '.pytest_cache'} or part.endswith('.egg-info') for part in relative.parts):
        continue
    if path.suffix in {'.sqlite', '.db', '.log', '.dll', '.exe'} or path.name.endswith(('.sqlite-wal', '.sqlite-shm')):
        errors.append(f'Unexpected private data or binary runtime: {relative}')
    if path.suffix.lower() in text_extensions:
        value = path.read_text(encoding='utf-8-sig')
        if private_path.search(value):
            errors.append(f'Private machine path: {relative}')
# Git blobs are canonical; Windows checkout line endings may differ.
source_manifest = json.loads((ROOT / 'source-manifest.json').read_text(encoding='utf-8'))
source_entries = {item['path']: item for item in source_manifest['files']}
canonical = None
try:
    probe = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=ROOT, capture_output=True, text=True)
    if probe.returncode == 0 and Path(probe.stdout.strip()).resolve() == ROOT.resolve():
        records = [r for r in subprocess.check_output(['git', 'ls-files', '--stage', '-z'], cwd=ROOT).split(b'\0') if r]
        index = {r.split(b'\t', 1)[1].decode('utf-8'): r.split(b'\t', 1)[0].split()[1] for r in records}
        if set(index) != set(source_entries) | {'source-manifest.json'}:
            errors.append('Source manifest membership differs from Git')
        oids = sorted(set(index.values()))
        stream = io.BytesIO(subprocess.check_output(['git', 'cat-file', '--batch'], cwd=ROOT, input=b'\n'.join(oids)+b'\n'))
        blobs = {}
        for oid in oids:
            header = stream.readline().split()
            if header[:2] != [oid, b'blob']:
                raise ValueError('Unexpected Git object in source set')
            blobs[oid] = stream.read(int(header[2]))
            if stream.read(1) != b'\n':
                raise ValueError('Incomplete Git source object')
        canonical = {name: blobs[oid] for name, oid in index.items()}
except FileNotFoundError:
    pass  # Source ZIP verification also works without Git installed.
for relative, item in source_entries.items():
    source_path = ROOT / relative
    if not source_path.is_file():
        errors.append('Source manifest file missing: '+relative)
        continue
    data = canonical.get(relative, b'') if canonical is not None else source_path.read_bytes()
    if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
        errors.append('Source manifest hash mismatch: '+relative)
report = {'implementation_files': len(expected), 'source_manifest_files': len(source_entries), 'components': MANIFEST['components'], 'errors': errors}
print(json.dumps(report, ensure_ascii=False, indent=2))
sys.exit(1 if errors else 0)
