"""Shared Japanese labels for template diagnostics; standard library only."""
LABELS = {'ok':'取得完了', 'needs_review':'要確認', 'not_applicable':'適用不可',
          'missing':'候補なし', 'empty':'空文字・空白のみ', 'unsupported':'未対応の文字方向'}
REASONS = {'PAGE_COUNT_MISMATCH':'ページ数が一致しません', 'PAGE_SIZE_MISMATCH':'ページ寸法が一致しません',
           'PAGE_ROTATION_MISMATCH':'ページ回転が一致しません', 'PAGE_ONLY_APPLICABILITY':'適用条件なし：ページ情報だけで判定します',
           'CONDITION_MISMATCH':'適用条件が一致しません', 'NO_TEXT':'候補なし', 'EMPTY_TEXT':'空文字・空白のみ',
           'UNSUPPORTED_ROTATION':'回転文字を含みます', 'UNSUPPORTED_DIRECTION':'縦書きを含みます',
           'ORIGIN_INVALID':'由来情報が不正です', 'ORIGIN_FOREIGN':'別文書の由来情報です',
           'ORIGIN_PARTIAL':'由来情報の一部が不正です'}


def diagnostic_message(code):
    name, _, page = code.partition(':')
    return REASONS.get(name, name) + (f'（ページ{page}）' if page else '')
