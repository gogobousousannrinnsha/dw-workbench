"""Portable entry; paths are relative to the installation, never the shell cwd."""
from datetime import datetime
import os
from pathlib import Path
import sys
import uuid


def main(argv=None):
    root=Path(__file__).resolve().parents[1]
    os.environ['DW_OCR_CACHE']=str(root/'cache')
    os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK']='True'
    from docuworks_integrations.settings import load_settings
    from docuworks_integrations.jobs import process_documents
    arguments=list(sys.argv[1:] if argv is None else argv)
    settings=load_settings(root/'settings.ini')
    if settings.font:
        from dataclasses import replace
        settings=replace(settings,font=str((root/settings.font).resolve()))
    job='job-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
    result=process_documents(arguments or [root/'INPUT'],root/'OUTPUT'/job,root/'runs'/job,
        root/'models',settings=settings,review=True,
        excluded=[root/p for p in ('OUTPUT','runs','cache','ocr-cache','runtime','models')])
    print('\n'+('対象のXDW文書がありません。INPUTまたは指定フォルダを確認してください。'
          if result['status']=='NO_INPUT' else '処理結果: '+result['status']))
    for name in ('ocr','review','rectangles','text_maps'):
        c=result['counts'][name]
        print(f"{name}: 成功 {c['SUCCEEDED']} / 失敗 {c['FAILED']} / 未処理 {c['PENDING']}")
    print('保存先: '+str(root/'OUTPUT'/job))
    for record in result['documents']:
        if record.get('review')=='SUCCEEDED':
            print('校正する文書: '+str(root/'OUTPUT'/job/record['review_dir']/'review.xdw'))
    if result['counts']['review']['SUCCEEDED']:
        print('Viewerで編集・保存して閉じた後、review.xdwを「校正結果取込.bat」へドロップしてください。')
    return result['exit_code']


if __name__=='__main__':
    try: code=main()
    except KeyboardInterrupt: code=130; print('中断しました。',file=sys.stderr)
    except Exception as exc: code=1; print(f'{type(exc).__name__}: {exc}',file=sys.stderr)
    raise SystemExit(code)
