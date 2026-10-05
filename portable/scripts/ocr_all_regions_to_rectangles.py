"""Legacy CLI adapter to the common document workflow; bundles are always kept."""
import argparse
from pathlib import Path
import shutil
import uuid
from docuworks_integrations import process_documents
from docuworks_integrations.settings import Settings


def main():
    root=Path(__file__).resolve().parents[1]
    p=argparse.ArgumentParser()
    p.add_argument('input_xdw',type=Path)
    p.add_argument('--output',type=Path)
    p.add_argument('--model-root',type=Path,default=root/'models')
    p.add_argument('--dll-path',type=Path)
    p.add_argument('--dpi',type=int,default=300)
    p.add_argument('--padding-mm',type=float,default=.5)
    p.add_argument('--min-confidence',type=float,default=0.)
    p.add_argument('--color',default='red')
    p.add_argument('--runs-dir',type=Path,default=root/'runs')
    p.add_argument('--keep-runs',action='store_true',help='Compatibility flag; runs are always retained')
    a=p.parse_args()
    output=a.output or a.input_xdw.with_name(a.input_xdw.stem+'_ocr_rectangles.xdw')
    if output.exists(): raise FileExistsError(output)
    job='job-'+uuid.uuid4().hex[:12]
    destination=root/'OUTPUT'/job
    result=process_documents([a.input_xdw],destination,a.runs_dir/job,a.model_root,dll_path=a.dll_path,
        settings=Settings(dpi=a.dpi,padding_mm=a.padding_mm,min_confidence=a.min_confidence,color=a.color))
    generated=destination/'doc-000001/annotated.xdw'
    if generated.is_file():
        with output.open('xb') as dst,generated.open('rb') as src: shutil.copyfileobj(src,dst)
    print(destination)
    return result['exit_code']


if __name__=='__main__': raise SystemExit(main())
