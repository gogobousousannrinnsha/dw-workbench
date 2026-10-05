"""Populate only an already-copied local verification Portable; no publishing."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def repair_launcher(data):
    data=re.sub(rb'docuworks-ctypes==[^\s"]+',b'docuworks-ctypes==1.0.1',data)
    return re.sub(rb'docuworks-integrations==[^\s"]+',b'docuworks-integrations==0.12.0+reviewab.1',data)


def main():
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True)
    p.add_argument('--portable',type=Path,required=True);p.add_argument('--wheel',type=Path,required=True)
    args=p.parse_args();repo=args.repo.resolve();root=args.portable.resolve()
    if not (root/'runtime/python.exe').is_file(): raise ValueError('Copy the baseline Portable first')
    for folder in ('INPUT','OUTPUT','runs','cache','templates','template-drafts','logs'):
        (root/folder).mkdir(exist_ok=True)
    for name in ('ocr開始（一括）.bat','ocr開始（分割）.bat',
                 'A_一括作成.bat','B_ページ別作成と結合.bat','比較結果作成.bat','README_AB.md'):
        data=(repo/'portable'/name).read_text(encoding='utf-8')
        (root/name).write_bytes(data.replace('\r\n','\n').replace('\n','\r\n').encode('utf-8'))
    for name in ('start_ab.py','compare_ab.py'):
        shutil.copyfile(repo/'portable/scripts'/name,root/'scripts'/name)
    # Keep the full embedded project source aligned with the candidate wheel.
    files=subprocess.check_output(['git','-C',str(repo),'ls-files','--cached','--others','--exclude-standard','-z']).decode().split('\0')
    for name in files:
        if name.startswith('packages/docuworks-integrations/') or name in (
                'scripts/verify_review_ab.py','scripts/verify_review_ab_portable.py','scripts/prepare_review_ab.py',
                'scripts/finalize_review_ab.py','docs/review-ab-verification-20260930.md'):
            target=root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(repo/name,target)
    shutil.copyfile(args.wheel,root/'wheelhouse'/args.wheel.name)
    pin=root/'repair_project_wheels.bat'
    pin.write_bytes(repair_launcher((repo/'portable/repair_project_wheels.bat').read_bytes()))
    wheels=root/'reference/project-wheels.json'
    old=json.loads(wheels.read_text(encoding='utf-8'))
    old={k:v for k,v in old.items() if not k.startswith('docuworks_integrations-')}
    old[args.wheel.name]=hashlib.sha256(args.wheel.read_bytes()).hexdigest()
    wheels.write_text(json.dumps(old,indent=2)+'\n',encoding='utf-8')
    baseline=root/'reference/distribution-files.baseline-v061.json'
    if not baseline.exists(): shutil.copyfile(root/'reference/distribution-files.json',baseline)
    description=dict(kind='local-review-ab-verification',base_release='v0.6.1',
        base_commit='ae4c27a46a7bc0a628ff7beb9a750a5b234de88f',integrations='0.12.0+reviewab.1',
        core='1.0.1',wheel_sha256=hashlib.sha256(args.wheel.read_bytes()).hexdigest(),published=False)
    (root/'reference/review-ab-build.json').write_text(json.dumps(description,indent=2)+'\n',encoding='utf-8')
    patch=subprocess.check_output(['git','-C',str(repo),'diff','HEAD','--binary'])
    (root/'reference/tracked-changes.patch').write_bytes(patch)
    # Full new source files also travel with the Portable; the inventory records their hashes.
    (root/'README.txt').write_text('DW-OCR A/B検証版\n\nREADME_AB.mdを参照してください。\nocr開始（一括）.bat / ocr開始（分割）.bat\n両方とも元のXDWからOCRします。\n',encoding='utf-8-sig')
    print(root)


if __name__=='__main__': main()
