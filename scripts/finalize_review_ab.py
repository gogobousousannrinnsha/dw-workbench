"""Freeze the local kit inventory and archive only the known smoke-test jobs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path)
    args=parser.parse_args();task=args.root.resolve();root=task/'Portable'
    sys.path.insert(0,str(root/'runtime/Lib/site-packages'))
    from docuworks_integrations._authoring_storage import locked
    validation=task/'validation';record_path=validation/'portable-smoke/validation.json'
    record=json.loads(record_path.read_text(encoding='utf-8'))
    with locked(root):
        if 'archived_from' not in record:
            expected={Path(p).resolve() for p in record['jobs'].values()}
            actual={p.resolve() for p in (root/'OUTPUT').glob('*/job-*')}
            if actual!=expected:raise RuntimeError('Unexpected jobs; do not move user output')
            if any((root/'INPUT').iterdir()):raise RuntimeError('Unexpected user input')
            archive=validation/'portable-smoke/results';archive.mkdir(exist_ok=False)
            for name in ('OUTPUT','runs','logs'):
                source=(root/name).resolve();destination=(archive/name).resolve()
                if not source.is_relative_to(root) or not destination.is_relative_to(validation):
                    raise ValueError('Unexpected archive path')
                # This verification task owns these three trees. No shell/path composition.
                shutil.move(str(source),str(destination));source.mkdir()
            record['archived_from']=dict(record['jobs'])
            record['jobs']={k:str(archive/Path(v).relative_to(root)) for k,v in record['jobs'].items()}
            record_path.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        baseline=json.loads((root/'reference/distribution-files.baseline-v061.json').read_text(encoding='utf-8'))
        before={r['path']:r['sha256'] for r in baseline['files']}
        volatile={'INPUT','OUTPUT','runs','logs','cache','ocr-cache','templates','template-drafts'}
        inventory_path='reference/distribution-files.json'
        rows=[]
        for path in sorted(root.rglob('*')):
            if not path.is_file():continue
            rel=path.relative_to(root)
            if rel.parts[0] in volatile or '__pycache__' in rel.parts or str(rel)=='.authoring.lock':continue
            name=rel.as_posix()
            if name==inventory_path:continue
            digest=sha(path)
            origin='baseline' if before.get(name)==digest else 'verification'
            rows.append(dict(path=name,bytes=path.stat().st_size,sha256=digest,origin=origin))
        inventory=dict(schema='dw-ocr-distribution-files',schema_version='1.0',candidate=True,
            purpose='local-review-ab-verification',excluded_self=inventory_path,
            excluded_mutable_roots=sorted(volatile),excluded_generated=['__pycache__','.authoring.lock'],
            baseline_sha256='cd11f10d0dcd755ae2683d0a8a159d8d12fb121894bf7c1dab50ee37de6554a7',files=rows)
        (root/inventory_path).write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        for row in rows:
            assert sha(root/row['path'])==row['sha256'],row['path']
        wheel=task/'dist/docuworks_integrations-0.12.0+reviewab.1-py3-none-any.whl'
        with zipfile.ZipFile(wheel) as z:
            members=[n for n in z.namelist() if n.startswith('docuworks_integrations/')]
            assert all((root/'runtime/Lib/site-packages'/n).read_bytes()==z.read(n) for n in members)
        result=dict(static_inventory_files=len(rows),inventory_verified=True,
            inventory_sha256=sha(root/inventory_path),installed_wheel_members=len(members),
            installed_wheel_matches=True,wheel_sha256=sha(wheel),smoke_outputs_archived=True,
            input_output_runs_empty=all(not any((root/n).iterdir()) for n in ('INPUT','OUTPUT','runs')))
        (validation/'artifact-checks.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result))


if __name__=='__main__':main()
