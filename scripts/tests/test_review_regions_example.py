"""The multi-region example composes the existing correction transaction."""
from pathlib import Path
import subprocess
import sys


def test_multi_region_example(tmp_path):
    root=Path(__file__).resolve().parents[2]
    code='''
import sys,importlib.util,json
from pathlib import Path
root,tmp=map(Path,sys.argv[1:])
sys.path.insert(0,str(root/'packages/docuworks-integrations'))
sys.path.insert(0,str(root/'packages/docuworks-integrations/tests'))
from test_review_xdw_regions import multi_run,FakeSdk,read,write,IDS
from docuworks_integrations import review_xdw
original=multi_run(tmp)
review_xdw._SdkBackend=lambda dll:FakeSdk(original.pages[1])
spec=importlib.util.spec_from_file_location('example',root/'examples/use_review_xdw_regions.py')
example=importlib.util.module_from_spec(spec);spec.loader.exec_module(example)
folder=example.prepare(original.root,list(reversed(IDS)),tmp/'review')
data=read(folder/'review.xdw');data['annotations'][0]['text']='corrected'
edited=tmp/'edited.xdw';write(edited,data)
out=example.finish(original.root,folder,edited,tmp)
rows=[json.loads(line) for line in out.read_text(encoding='utf-8').splitlines()]
assert sum(row['is_corrected'] for row in rows)==1
assert rows[1]['text']=='corrected' and rows[2]['text']==original.pages[1].regions[1].text
'''
    subprocess.run([sys.executable,'-c',code,str(root),str(tmp_path)],check=True)
