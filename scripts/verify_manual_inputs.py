"""Check source-only manual inputs; generated PDF visual QA is separate."""
from pathlib import Path
import ast
import csv
import hashlib
import json
from openpyxl import load_workbook
from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / 'docs/manual-build'
for path in ROOT.glob('*.py'):
    ast.parse(path.read_text(encoding='utf-8-sig'), filename=path.name)
for path in ROOT.glob('*.json'):
    json.loads(path.read_text(encoding='utf-8-sig'))
pngs = list(ROOT.rglob('*.png'))
image_formats = {}
for path in pngs:
    with Image.open(path) as image:
        image_formats[image.format] = image_formats.get(image.format, 0) + 1
        image.verify()
demo = json.loads((ROOT / 'beginner_demo.json').read_text(encoding='utf-8-sig'))
source = ROOT / demo['input']
assert hashlib.sha256(source.read_bytes()).hexdigest() == demo['original_sha256']
workbook = load_workbook(ROOT / demo['xlsx'], read_only=True, data_only=False)
try:
    sheet = workbook['結果01']
    assert sheet['I2'].value == '000125' and sheet['I2'].data_type == 's'
    assert sheet['K2'].value == 179.8 and sheet['K2'].data_type == 'n'
    assert sheet['L2'].value == '℃'
finally:
    workbook.close()
csv_path = ROOT / demo['csv']
assert csv_path.read_bytes().startswith(b'\xef\xbb\xbf')
with csv_path.open(encoding='utf-8-sig', newline='') as stream:
    rows = list(csv.DictReader(stream))
assert len(rows) == 1 and rows[0]['部品番号'] == '000125' and rows[0]['測定温度'] == '179.8'
print(json.dumps({'manual_jsons': len(list(ROOT.glob('*.json'))), 'python_scripts': len(list(ROOT.glob('*.py'))), 'images': len(pngs), 'decoded_image_formats': image_formats, 'synthetic_source_sha256': demo['original_sha256'], 'synthetic_export_types': 'passed', 'scope': 'source inputs; generated PDF/HTML validation requires Release manual files'}, ensure_ascii=False, indent=2))
