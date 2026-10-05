# PaddleOCR空文字の再現と修正

基準は開発main `8f8d537`、変更はローカルの `fix/paddle-blank-text` です。
Integrations 0.7.0の未公開修正候補であり、公開Portable v0.3.0への反映は含みません。

## 修正の契約

`parse_paddle_result(payload, width, height)` の引数と戻り値（`tuple[OcrRegion, ...]`）は維持します。
Paddleの `rec_texts` に空文字または `str.strip()` で空になる文字列が含まれる場合、該当行を除外します。
正常文字は日本語・引用符・改行・前後空白を含めてそのまま保持し、座標・信頼度・相対順序も維持します。
`None`など文字列以外は引き続き `ValueError` です。配列長、座標、信頼度は空文字の行でも検証します。

変換が正常に完了し、除外件数が1件以上の場合のみ、標準loggingの
`docuworks_integrations.paddle` loggerからWARNINGを1回出します。
文言は `Skipped N blank OCR text region(s)` で、認識文字そのものを含めません。
標準設定ではstderrに出力されます。今回の検証ではstderrをログファイルへ保存します。
成功runの新しい診断ファイルやSchema項目は追加していません。

全件除外なら空tupleを返し、現行の複数ページ処理は `NO_TEXT_DETECTED` として保存します。
全ページが0件ならJSONLは空です。新しいrunの領域IDは除外後の順序で既存方式により採番します。
過去のrunとのID一致を保証する変更ではなく、保存済みrunや修正セットは変更しません。
`OcrRegion`、JSON入力、文字訂正APIの空白拒否、既存の失敗分類は緩和しません。

## 再現手順

GPU・Paddle・DocuWorks DLLは不要です。必要なPython依存はパッケージの試験環境とPillowです。
text-map画像の検証には `resolve_font()` が選択できるフォントも必要です。
`packages/docuworks-integrations` と `packages/docuworks-ctypes` をimportできる環境で、リポジトリルートから実行します。

```text
python scripts/reproduce_paddle_blank.py --fixture packages/docuworks-integrations/tests/fixtures/paddle-blank.json --output <新規の再現保存先> --expect before
python -m pytest packages/docuworks-integrations/tests/test_paddle_blank.py -p no:cacheprovider
```

最初のコマンドは修正前の `8f8d537` のパーサーで実行します。再現用スクリプトとfixtureはこの修正ブランチから取得します。
修正後には別の新規保存先を指定し、`--expect after`で実行します。
保存先が既にある場合は上書きせず拒否します。

人工入力は3領域 `ABC`、空文字、`DEF` です。直接変換では空白・タブ・改行・全角空白・`None`と正常対照も確認します。
3ページの2ページ目にその入力を渡し、基準版では `ValueError`、`phase=recognize`、`failure_scope=batch`、
失敗ページ2、完了済みページ1、完成manifestなし、生データ保存、次文書未処理を確認します。
修正後は同じ入力で全ページ保存・再読込・JSONL・後続文書まで完了します。

描画は人工画像を生成する代替、矩形は実際の計画作成をdry-runで実行します。
パーサー・保存・失敗分類・text-map画像作成・JSONLは実処理です。
人工source.xdwは実XDWではなく、SDKやViewerの動作確認には使っていません。

## 検証記録の読み方

製品コード修正前に再現が成立し、新しい期待値では **19件失敗・21件成功** を確認しました。
修正直後にテストの領域ID参照名を既存型の `id` に合わせ、修正後の40件が成功しました。
この参照名の修正は製品APIの変更ではありません。
修正前の記録は [before.json](../evidence/paddle-blank/before.json)、修正後・環境別・配布検証の要約は
[verification.json](../evidence/paddle-blank/verification.json) を参照してください。
入力SHA-256とパーサーのハッシュで対象を照合し、作業ツリーでの検証と確定コミットを区別します。

実際に報告された文書・失敗時rawは未提供です。
人工入力による同一障害の再現と修正を検証したもので、実文書の原因確定・再実行は未確認です。
同じ例外は `None` でも発生するため、例外文だけで実データに空文字があったとは断定できません。

## 最終検証と環境条件

| 検証 | 結果 |
|---|---|
| 最終fixtureを基準版へ入力 | 新しい期待値では19件失敗・21件成功 |
| Python 3.10〜3.13、新規試験 | 各40件成功 |
| Python 3.10〜3.13、人工入力の処理経路 | 全版で成功。3.12は下記の保存エラー後に新規保存先で再実行 |
| Python 3.11〜3.13、既存を含むIntegrations回帰 | 各325件成功 |
| Python 3.11〜3.13、配布処理 | 各80件成功 |
| 未加工sdist、訂正・レビュー・今回の修正 | 196件成功。外部ファイル補完なし、元ファイルの変更なし |
| 通常pip導入の最終wheel（Python 3.11） | pip check成功、325件成功 |
| 最終Integrations配布物と既存Core配布物 | 4配布物の監査成功 |

Python 3.10のライブラリ全体、実DLL・実GPU・Viewerでの新規検証は含みません。
wheelのテスト依存（pytest、Pillow、jsonschema等）は既存のPython 3.11試験環境から参照し、
製品2パッケージのimport先は新規wheel導入環境であることを検査しました。
sdistは別々のフォルダーでビルドと試験を実施し、pytestが生成したキャッシュ以外の追加・変更がないことを確認しました。

初回の配布処理試験ではpytest既定の一時フォルダーへのアクセスが拒否されました。
製品コードやセキュリティ設定を変更せず、既存のWindows向けtmp_path fixtureを試験実行器から読み込んで再試験しました。
Python 3.12の人工入力試験では一度、job.json確定時にWinError 32が発生しました。
原因プロセスは未特定です。失敗記録を保持し、新規保存先で単独再実行したところ成功しました。
ファイル共有問題への修正・再試行機能を今回追加したわけではありません。

初回sdistの人工fixtureは生OCR出力と同形だったため、配布監査に拒否されました。
監査ルールは変更せず、手書きのtext・score・polygonの組から入力を構築する人工レシピへ変更しました。
初回入力との値の完全一致、および最終fixtureでの基準版・修正版の双方の再現を確認しました。
初回候補は最終配布物として採用していません。
