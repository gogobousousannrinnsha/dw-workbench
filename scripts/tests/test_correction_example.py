"""Exercise the repository example without adding it to the package sdist."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import os
import pytest


@pytest.mark.parametrize('encoding', ['utf-8', 'cp1252'])
def test_correction_example(tmp_path, encoding):
    root = Path(__file__).resolve().parents[2]
    code = '''
import importlib.util, json, sys
from pathlib import Path
root, tmp = map(Path, sys.argv[1:])
sys.path.insert(0, str(root / 'packages/docuworks-integrations'))
sys.path.insert(0, str(root / 'packages/docuworks-integrations/tests'))
from test_corrections import run, edit
original = run(tmp)
spec = importlib.util.spec_from_file_location('example', root / 'examples/correct_saved_ocr.py')
example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)
output = example.correct_one(original.root, edit().region_id, edit().before_text, edit().after_text, tmp)
assert json.loads(output.read_text(encoding='utf-8').splitlines()[0])['text'] == edit().after_text
'''
    completed = subprocess.run([sys.executable, '-c', code, str(root), str(tmp_path)], check=True,
                               env=dict(os.environ, PYTHONIOENCODING=encoding), capture_output=True)
    assert 'p000' in completed.stdout.decode(encoding)
