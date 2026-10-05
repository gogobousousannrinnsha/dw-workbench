"""Repository review example composes the real correction API with a fake SDK."""
from pathlib import Path
import subprocess
import sys


def test_review_example(tmp_path):
    root=Path(__file__).resolve().parents[2]
    code='''
import sys, importlib.util
from pathlib import Path
root,tmp=map(Path,sys.argv[1:])
sys.path.insert(0,str(root/'packages/docuworks-integrations'))
sys.path.insert(0,str(root/'packages/docuworks-integrations/tests'))
from test_review_xdw import run, FakeSdk, read, write
from docuworks_integrations import review_xdw
original=run(tmp)
review_xdw._SdkBackend=lambda dll: FakeSdk(original.pages[1])
spec=importlib.util.spec_from_file_location('example',root/'examples/use_review_xdw.py')
example=importlib.util.module_from_spec(spec); spec.loader.exec_module(example)
folder=example.prepare(original.root,'p0002-r000001',tmp/'review')
data=read(folder/'review.xdw'); data['annotations'][0]['text']='corrected'
edited=tmp/'edited.xdw'; write(edited,data)
output=example.finish(original.root,folder,edited,tmp)
assert 'corrected' in output.read_text(encoding='utf-8')
'''
    subprocess.run([sys.executable,'-c',code,str(root),str(tmp_path)],check=True)
