"""One-document reviewed import for the bundled Python; no OCR dependency."""
from datetime import datetime
from pathlib import Path
import sys
import uuid


def input_path(prompt):
    value=input(prompt).strip().strip('"')
    if not value: raise ValueError('パスが指定されていません。')
    return Path(value)


def main(argv=None):
    from docuworks_integrations import load_review_session, import_reviewed_result
    args=list(sys.argv[1:] if argv is None else argv)
    if len(args)>1: raise ValueError('取り込みは1文書ずつです。XDWまたは校正フォルダーを1つ指定してください。')
    target=Path(args[0]) if args else input_path('編集済みXDWまたは校正フォルダーのパス: ')
    target=target.absolute()
    if target.is_symlink() or (hasattr(target,'is_junction') and target.is_junction()):
        raise ValueError('リンク経由の入力は使用できません。')
    if target.is_dir():
        session_dir=target
        edited=target/'review.xdw'
    else:
        if target.suffix.lower()!='.xdw' or not target.is_file():
            raise ValueError('保存済みのXDWファイルを指定してください。')
        edited=target
        session_dir=target.parent
        if not (session_dir/'session.json').is_file():
            session_dir=input_path('元の校正フォルダー（identity.jsonとsession.jsonがある場所）のパス: ')
    session=load_review_session(session_dir)
    parent=session.root.parent/'reviewed'
    # Reject a redirected output before mkdir; the API also validates ancestors.
    from docuworks_integrations.reviewed import _plain_path
    _plain_path(parent)
    parent.mkdir(exist_ok=True)
    output=parent/('result-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    result=import_reviewed_result(session.root,edited,output,validation_mode='identity')
    items=[i for p in result.pages for i in p['items']]
    print(f'取り込み完了: {len(result.pages)}ページ / {len(items)}文字項目')
    print('除外した付箋: '+str(result.data['excluded_sticky_count']))
    print('原本参照なし: '+str(sum(i['origin_evidence']['status']=='none' for i in items)))
    print('不正な参照を持つ項目: '+str(sum(i['origin_evidence']['status'] in ('invalid','foreign','partial') for i in items)))
    print('空文字・空白のみ: '+str(sum('EMPTY_TEXT' in i['diagnostics'] for i in items)))
    print('検証: ID照合済み／ページ構造未検証')
    print('保存先: '+str(result.root))
    print('校正後JSONL: '+str(result.root/'reviewed.jsonl'))
    return 0


if __name__=='__main__':
    try: code=main()
    except (KeyboardInterrupt,EOFError): code=130; print('取り込みを中断しました。',file=sys.stderr)
    except Exception as exc:
        code=1; print(f'取り込み失敗: {type(exc).__name__}: {exc}',file=sys.stderr)
        print('Viewerで保存して閉じ、元の校正フォルダーと対応するXDWを指定してください。',file=sys.stderr)
    raise SystemExit(code)
