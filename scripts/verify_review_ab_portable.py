"""Exercise the actual BATs with an existing disposable synthetic XDW fixture."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def bat(root, name, arguments, log):
    command='"'+os.environ['COMSPEC']+'" /d /s /c ""'+str(root/name)+'"'
    command+=''.join(' "'+str(a)+'"' for a in arguments)+'"'
    with log.open('wb') as stream:
        result=subprocess.run(command,input=b'\r\n',stdout=stream,stderr=subprocess.STDOUT,
                              timeout=900,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError(f'{name} failed ({result.returncode}); see {log}')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--portable',type=Path,required=True)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=args.portable.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    # Reject concurrent A/B entry before any OCR job is created.
    code="from pathlib import Path\nfrom docuworks_integrations._authoring_storage import locked\nimport sys\nwith locked(Path(sys.argv[1])):\n print('READY',flush=True)\n sys.stdin.readline()\n"
    python=root/'runtime/python.exe'
    holder=subprocess.Popen([str(python),'-I','-X','utf8','-c',code,str(root)],stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        assert holder.stdout.readline().strip()==b'READY'
        before=set((root/'OUTPUT').rglob('job-*'))
        locked=subprocess.run([str(python),'-I','-X','utf8',str(root/'scripts/start_ab.py'),'A',str(args.source)],
                              capture_output=True,timeout=45,creationflags=subprocess.CREATE_NO_WINDOW)
        (out/'lock-rejected.log').write_bytes(locked.stdout+locked.stderr)
        assert locked.returncode==1 and set((root/'OUTPUT').rglob('job-*'))==before
    finally:
        holder.communicate(input=b'\n',timeout=15)
    jobs={}
    for variant,name in [('A','A_一括作成.bat'),('B','B_ページ別作成と結合.bat')]:
        before=set((root/'OUTPUT'/variant).glob('job-*'))
        bat(root,name,[args.source],out/(variant+'-bat.log'))
        created=set((root/'OUTPUT'/variant).glob('job-*'))-before
        assert len(created)==1
        job=created.pop();jobs[variant]=job
        result=json.loads((job/'job.json').read_text(encoding='utf-8'))
        assert result['status']=='COMPLETE' and result['counts']['review']['SUCCEEDED']==1
        perf=json.loads((job/'performance.json').read_text(encoding='utf-8'))
        assert perf['status']=='COMPLETE' and perf['documents'][0]['pages']==3
        assert perf['memory']['sampled_peak_bytes'] is not None
        # The common import BAT must accept the resulting session.
        review=job/result['documents'][0]['review_dir']/'review.xdw'
        bat(root,'校正結果取込.bat',[review],out/(variant+'-import-bat.log'))
        imports=list((review.parent.parent/'reviewed').glob('result-*/reviewed.json'))
        assert len(imports)==1
    bat(root,'比較結果作成.bat',[jobs['A'],jobs['B'],out/'comparison'],out/'comparison-bat.log')
    record=dict(synthetic_document=True,real_ocr_executed=True,bat_A=True,bat_B=True,
                pages=3,blank_page=True,mixed_sizes=True,concurrent_start_rejected=True,
                common_import_bat_A=True,common_import_bat_B=True,comparison_bat=True,
                jobs={k:str(v) for k,v in jobs.items()})
    (out/'validation.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(record,ensure_ascii=False))


if __name__=='__main__':main()
