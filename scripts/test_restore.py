from __future__ import annotations
import hashlib
import io
import json
import os
import tempfile
import uuid
from pathlib import Path
import shutil
import subprocess
import zipfile

# Synthetic fixtures exercise restoration only. The runtime file is a sentinel.
ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'scripts' / 'Restore-Portable.ps1'
OUTPUT_PARENT = Path(os.environ.get('DW_WORKBENCH_RESTORE_TEST_ROOT', tempfile.gettempdir()))
OUTPUT_PARENT.mkdir(parents=True, exist_ok=True)
TEST_ROOT = OUTPUT_PARENT / ('dw-restore-tests-' + uuid.uuid4().hex[:8])
TEST_ROOT.mkdir(exist_ok=False)
PS = str(Path(os.environ['SystemRoot']) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe')
REPORT = []

def fixture(name, entries=None):
    folder = TEST_ROOT / name
    folder.mkdir()
    shutil.copyfile(HELPER, folder / 'Restore-Portable.ps1')
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for entry, content in (entries or {'DW-Workbench-v0.2.0/runtime/python.exe': b'synthetic-runtime', 'DW-Workbench-v0.2.0/projects/': b'', 'DW-Workbench-v0.2.0/readme.txt': b'synthetic fixture'}).items():
            archive.writestr(entry, content)
    raw = stream.getvalue()
    parts = []
    for index, data in enumerate((raw[:len(raw)//2], raw[len(raw)//2:]), 1):
        name = f'Portable.zip.{index:03}'
        (folder / name).write_bytes(data)
        parts.append({'name': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    manifest = {'format': 'dw-workbench-portable-parts-v1', 'root_directory': 'DW-Workbench-v0.2.0', 'zip': {'name': 'Portable.zip', 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}, 'parts': parts}
    (folder / 'PORTABLE-MANIFEST.json').write_text(json.dumps(manifest), encoding='utf-8')
    return folder, raw, manifest

def run(name, folder, success, *, extract=True, destination=None):
    args = [PS, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(folder / 'Restore-Portable.ps1')]
    if extract:
        args += ['-Extract']
    if destination:
        args += ['-Destination', str(destination)]
    result = subprocess.run(args, cwd=folder, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    output = result.stdout.decode('utf-8', errors='replace') + result.stderr.decode('utf-8', errors='replace')
    (folder / (name + '.txt')).write_text(output, encoding='utf-8')
    passed = (result.returncode == 0) == success
    REPORT.append({'case': name, 'exit_code': result.returncode, 'passed': passed})
    assert passed, output
    if not success:
        logs = list(folder.glob('Restore-Portable-error-*.txt'))
        assert logs, 'Missing error log'
        assert 'Phase: ' in logs[-1].read_text(encoding='utf-8-sig')
    return output

folder, raw, manifest = fixture('日本語 空白の正常復元')
run('merge-extract-Japanese-space-path', folder, True)
assert (folder / 'Portable.zip').read_bytes() == raw
target = folder / 'DW-Workbench-v0.2.0'
assert (target / 'runtime/python.exe').read_bytes() == b'synthetic-runtime'
assert (target / 'projects').is_dir()
(target / 'user-project.sqlite').write_bytes(b'user-work-preserved')
run('reject-existing-portable', folder, False)
assert (target / 'user-project.sqlite').read_bytes() == b'user-work-preserved'
run('reuse-complete-verified-zip', folder, True, extract=False)
folder, raw, manifest = fixture('missing-part')
(folder / 'Portable.zip.002').unlink()
run('reject-missing-part', folder, False)
assert not (folder / 'Portable.zip').exists()
folder, raw, manifest = fixture('corrupt-part')
(folder / 'Portable.zip.001').write_bytes(b'bad')
run('reject-corrupt-part', folder, False)
assert not (folder / 'Portable.zip').exists()
folder, raw, manifest = fixture('incorrect-existing-zip')
(folder / 'Portable.zip').write_bytes(b'existing work')
run('preserve-incorrect-existing-zip', folder, False)
assert (folder / 'Portable.zip').read_bytes() == b'existing work'
for name, entry in [('traversal', 'DW-Workbench-v0.2.0/../../outside.txt'), ('wrong-root', 'other/runtime/python.exe'), ('drive', 'DW-Workbench-v0.2.0/C:/outside.txt'), ('reserved', 'DW-Workbench-v0.2.0/NUL.txt'), ('trailing-dot', 'DW-Workbench-v0.2.0/dir./file.txt')]:
    folder, raw, manifest = fixture(name, {entry: b'invalid path'})
    run('reject-' + name, folder, False)
    assert not list(folder.glob('._dw-*')), 'Invalid archive created staging'
folder, raw, manifest = fixture('manifest-traversal')
manifest['zip']['name'] = '../outside.zip'
(folder / 'PORTABLE-MANIFEST.json').write_text(json.dumps(manifest), encoding='utf-8')
run('reject-manifest-traversal', folder, False)
folder, raw, manifest = fixture('case-duplicate', {'DW-Workbench-v0.2.0/runtime/python.exe': b'1', 'DW-Workbench-v0.2.0/runtime/PYTHON.exe': b'2'})
run('reject-case-duplicate', folder, False)
assert not list(folder.glob('._dw-*'))
folder, raw, manifest = fixture('runtime-missing', {'DW-Workbench-v0.2.0/notes.txt': b'no runtime'})
output = run('runtime-missing-keeps-ZIP-and-diagnostics', folder, False)
assert (folder / 'Portable.zip').read_bytes() == raw
assert not (folder / 'DW-Workbench-v0.2.0').exists()
assert 'Incomplete extraction:' in output
folder, raw, manifest = fixture('mid-extraction-conflict', {'DW-Workbench-v0.2.0/runtime/python.exe': b'synthetic-runtime', 'DW-Workbench-v0.2.0/block': b'a file', 'DW-Workbench-v0.2.0/block/child.txt': b'failure'})
output = run('mid-extraction-conflict-keeps-ZIP-and-identifies-entry', folder, False)
assert 'ZIP entry: DW-Workbench-v0.2.0/block/child.txt' in output
assert (folder / 'Portable.zip').read_bytes() == raw
assert not (folder / 'DW-Workbench-v0.2.0').exists()
assert len(list(folder.glob('._dw-*'))) == 1
folder, raw, manifest = fixture('alternate-destination')
destination = TEST_ROOT / '日本語 空白 別の展開先'
destination.mkdir()
run('alternate-destination', folder, True, destination=destination)
assert (destination / 'DW-Workbench-v0.2.0/runtime/python.exe').read_bytes() == b'synthetic-runtime'
assert not (folder / 'DW-Workbench-v0.2.0').exists()
folder, raw, manifest = fixture('legacy-temp-residue')
old_stage = folder / 'DW-Workbench-extract-existing-residue'
old_stage.mkdir()
(old_stage / 'partial-user-data').write_bytes(b'preserved')
run('retry-ignores-and-preserves-old-staging', folder, True)
assert (old_stage / 'partial-user-data').read_bytes() == b'preserved'
assert not list(folder.glob('._dw-*'))
report = {'helper_sha256': hashlib.sha256((HELPER).read_bytes()).hexdigest(), 'passed': len(REPORT), 'cases': REPORT}
(TEST_ROOT / 'helper-tests.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'Restore helper: {len(REPORT)} tests passed')
print(f'Evidence: {TEST_ROOT / "helper-tests.json"}')
