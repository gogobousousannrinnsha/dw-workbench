import hashlib, json, os, struct, subprocess, sys
from importlib.metadata import version
from pathlib import Path

root = Path(__file__).resolve().parent
models = root / 'models'
print('Python:', sys.version.replace('\n', ' '))
print('64-bit:', struct.calcsize('P') == 8)
assert sys.version_info[:3] == (3, 13, 15)
assert struct.calcsize('P') == 8
for name in ('docuworks-ctypes','docuworks-integrations','paddlepaddle-gpu','paddleocr','paddlex','Pillow'):
    print(f'{name}: {version(name)}')
import docuworks_ctypes, docuworks_integrations
import paddle, paddleocr, paddlex
assert paddle.is_compiled_with_cuda(), 'Paddle is not CUDA-enabled'
print('Paddle CUDA build: yes')
print('Visible CUDA devices:', paddle.device.cuda.device_count())
baseline = json.loads((models / 'model-baseline.json').read_text(encoding='utf-8-sig'))
for entry in baseline:
    for rel, expected in entry['files'].items():
        path = models / rel.replace('\\', '/')
        assert path.is_file(), f'Missing model file: {path}'
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == expected, f'Model hash mismatch: {path}'
    print(entry['name'] + ': extracted file hashes OK')
dll = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'System32' / 'xdwapi.dll'
print('System XDWAPI:', str(dll), 'FOUND' if dll.is_file() else 'NOT FOUND (DocuWorks must be installed separately)')
try:
    result = subprocess.run(['nvidia-smi'], capture_output=True, text=True, timeout=15)
    print('nvidia-smi:', 'OK' if result.returncode == 0 else 'FAILED')
except Exception:
    print('nvidia-smi: NOT AVAILABLE')
print('Environment integrity: OK')
