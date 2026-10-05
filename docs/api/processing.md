# 派生出力と文書処理（現行Integrations 0.7.0）

開発候補のPaddleアダプターは、空文字・空白だけの認識行を座標・信頼度の検証後に除外します。
正常文字は加工せず、全件除外されたページは `NO_TEXT_DETECTED` とします。
除外件数は標準loggingに出力し、生のPaddle結果・公開API・保存形式は維持します。
公開Portable v0.3.0には未反映です。[詳細と再現検証](../maintainer/PADDLE_BLANK_TEXT.md)

開発の正本から公開用ソースを生成し、そのソースから作った同一wheelを開発検証とPortableに使用します。Core 1.0.0の機能コード、Result 1.0/1.1、旧run移行、Marker契約は維持します。マーカーの13pt上限問題は別課題です。

## 利用方法

対応するWindows x64、DocuWorks、NVIDIA GPU環境にアプリ全体を配置してください。Python 3.13、Paddle GPU 3.2.2 CUDA 12.9、PaddleOCR 3.7.0、PaddleX 3.7.2、PP-OCRv6 mediumを同梱します。

`INPUT`直下にXDWを置いて`OCR開始.bat`をダブルクリックするか、XDW・フォルダをBATへドロップします。複数対象に対応し、重複・リンク・管理フォルダを除外します。原本は保持され、毎回新しいjobを作ります。終了画面のOCR・矩形・確認画像の成功／失敗／未処理件数を確認してください。

`settings.ini`の`[ocr]`でrecursive、dpi（300/600）、min_confidence（0～1）、padding_mm（0以上）、minimum_mm（3以上）、color（red/blue/green/black/yellow/purple/teal）、font、jsonlを設定できます。未知の項目・不正値は開始前に拒否します。fontはアプリからの相対パスまたは絶対パスです。空ならWindowsの日本語フォントを探します。適切なフォントがなければエラーになります。

出力は`OUTPUT/job-.../doc-000001/`、元のOCR bundleは`runs/job-.../doc-000001/`です。job.jsonのrun参照は相対パスです。停止後にアプリ全体を移動できます。SDK画像パスが255 UTF-16単位を超える場合は、短い配置先へ移してください。

Windows上のPaddle 3.2.2はモデル名のファイル操作にANSI文字コードを使用するため、モデル初期化時だけローカルモデルパスをその文字コードで渡します。日本語Windowsの日本語配置先に対応します。現在のWindowsコードページで表現できない文字を含む場合は、英数字の配置先が必要です。Paddle本体やモデルは変更しません。初期化は逐次実行が前提です。

## 保存結果だけを利用するAPI

```python
from docuworks_integrations import annotate_rectangles, render_text_maps, process_documents
annotate_rectangles('saved-run', 'new.xdw', dry_run=True)
render_text_maps('saved-run', 'new-text-maps', font='JapaneseFont.ttc')
```

`annotate_rectangles(run_dir, output_xdw, *, input_xdw=None, dry_run=False, dll_path=None, padding_mm=.5, min_confidence=0., color='red', minimum_mm=3., report_path=None)`は保存runの原本コピーを使います。外部原本指定時はハッシュ一致が必須です。文書全体を一度保存し、再オープン後に注釈数・種類・位置・寸法・色・塗りなし・1pt線幅を照合します。既存注釈と未処理ページの注釈数・種類・位置・寸法も照合します。返り値は計画と検証辞書です。dry-runはファイルもDLL操作も行いません。

`render_text_maps(run_dir, output_dir, *, font=None, min_confidence=0., page=None, draw_boxes=True)`はPillowのみを必要とします。元画像と同じピクセル寸法の白地文字図と元画像への文字重ね図、レポートを新規ディレクトリへ保存します。OCR本文は変更しません。文字の組版再現や校正結果を意味する画像ではありません。

`process_documents(inputs, output_dir, runs_dir, model_root, *, settings=None, dll_path=None, excluded=(), engine=None)`は新規jobを生成します。Settingsは`docuworks_integrations.settings`で公開します。1つのエンジンを逐次再利用し、各文書の全ページを1runへ保存します。正常0件ページも保存し、空の画像と注釈追加なしのXDWを生成します。文書固有のSDKエラーは記録して続行し、共有環境・保存領域・整合性・未知のエラーは停止します。返却辞書のexit_codeは成功0、失敗1、中断130です。入力検証の失敗は例外です。

CLIは同名のハイフン区切りです。`--help`で引数を確認してください。`process-documents`は`--settings`を受け取ります。旧ocr-xdwの既定は1ページのままです。JSONLは`export-ocr`で再OCRせず作成できます。

## 互換入口

| 項目 | 旧公開版 | 統合版 |
|---|---|---|
| 標準入口 | ocr_rectangles.batへXDW指定 | OCR開始.bat、INPUT／複数ドロップ |
| OCR保存 | ページごとの独立run | 全処理ページを文書単位の1run |
| bundle保持 | スクリプト設定依存 | 常に保持 |
| 確認画像 | bundle内部 | OUTPUTまたは明示的新規ディレクトリ |
| --overwrite | bundle内を更新 | 拒否、新しい出力先が必要 |
| 旧矩形入口 | 独自OCR実装 | 共通workflowへの薄いラッパー |
| 旧ページ別run | 独立run | 独立runとして読込み、自動結合なし |

旧`ocr_rectangles.bat`の出力指定は維持し、共通jobも保存します。`text_maps.bat`の既定出力はrunの隣の`<run名>-text-maps`です。過去の絶対原本パスが無効でも新consumerはbundle内コピーを使用します。既存mark-regionの原本照合条件は変わりません。

## 保存と失敗の契約

### 保存失敗時の扱い

完成時のrename、ハッシュ照合、原本不変、XDW保存・再オープン検証、既存出力の上書き拒否は維持しています。一時保存の確定と後片付けは共通処理にまとめ、後片付けにも失敗した場合は元のエラーを残し、残存パスを補足します。job.jsonの内容が同一の更新は省き、変更がある場合のfsyncとatomic replaceは維持します。

OCR失敗時は診断データを一時領域に残し、追加のフォルダ移動は行いません。失敗runのerror.jsonにあるdiagnosticsは、そのerror.jsonのディレクトリを基準とする相対参照です。従来のrun/diagnosticsへの移動は行わないため、診断データを調べる場合はこの参照を使用してください。進捗記録にもエラーの補足と診断先を記録します。

`.recognition-`と12桁の16進数、または`.ocr-`と32桁の16進数から成るディレクトリ名は内部一時領域用に予約します。これらは完成manifestが残っていても公開のload_ocr_resultで拒否し、完成runの出力名にも指定できません。旧形式へのフォールバックにも進みません。完成後の通常runとResult 1.0/1.1の読込み契約は維持します。

フォルダ操作の事前チェックはjob開始時に1回だけ実施し、アクセス拒否時にはOCRを開始しません。事前チェック自体の後片付けに失敗した場合も停止します。Nortonの許可要求をなくすことを保証する変更ではなく、保護設定の変更やアクセス拒否後の迂回処理は行いません。

契約／配布監査、GPU・SDK保存再オープン、Viewer目視は別々に記録します。Viewerでは修復警告なし・矩形位置・可読性・選択編集・再保存を確認します。確認画像の文字と位置も目視対象です。公開済み基準と現在の候補の検証は[履歴案内](../history/README.md)で区別します。

## OCR専用バッチとの違い

ocr_folder(input_dir, batch_dir, model_root, *, recursive=False, dpi=300, dll_path=None, engine=None)はOCRだけを順次処理し、batch.jsonと配下のrunsを保存します。対象0件は事前エラーです。process_documentsは複数ファイル・フォルダーを受け取り、別々のoutput/runsとjob.jsonを作り、矩形・画像・任意JSONLまで扱います。対象0件はNO_INPUTです。両者は同じrecognitionを使いますが、返却形式と保存構成が異なるため別APIとして維持します。[バッチ詳細の継承契約](../history/BATCH_0.5.0.md)も参照できます。
