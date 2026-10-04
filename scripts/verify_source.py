"""Verify fixed implementation hashes and publication boundaries without imports."""
from pathlib import Path
import hashlib
import json
import re
import sys

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
report = {'implementation_files': len(expected), 'components': MANIFEST['components'], 'errors': errors}
print(json.dumps(report, ensure_ascii=False, indent=2))
sys.exit(1 if errors else 0)
