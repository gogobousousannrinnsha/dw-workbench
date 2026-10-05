> 履歴資料：整理前の記述を保存しています。現在の仕様・公開状況は[文書案内](../README.md)を参照してください。

# Integrations 0.5.0：フォルダバッチOCR

## 実行

Python 3.13、Core 1.0.0、CUDA 12.9版Paddle GPU 3.2.2、PP-OCRv6 mediumの既存環境を使用します。導入は[SETUP](../SETUP.md)を参照してください。

```powershell
python -m docuworks_integrations ocr-folder --input-dir local-data/input --batch-dir local-data/batch-001 --model-root models --dpi 300
python -m docuworks_integrations ocr-folder --input-dir local-data/input --batch-dir local-data/batch-002 --model-root models --recursive --dpi 300
```

通常は入力フォルダ直下だけ、--recursiveでサブフォルダも処理します。各XDWの全ページを1 runへ保存します。拡張子は大小文字を区別せず、相対パスのcasefold順、同順位は元の相対パス順です。同名ファイルでも別文書として扱います。リンク・Windows reparse point（ジャンクション等）は除外します。開始時の対象一覧に実行中の追加ファイルは含めません。

出力は存在しない新規ディレクトリを指定し、入力フォルダ自身や配下には置けません。対象0件、DPI不正、長すぎるSDK出力パスは出力作成前に拒否します。DPIは300/600、DLLは--dll-pathで指定できます。SDKには255 UTF-16コード単位の画像パス制限があるため、出力先は短いパスを使用してください。

既存ocr-xdwは引数省略なら1ページ目、--all-pagesなら1文書の全ページです。フォルダコマンドにはページ選択を設けていません。

## 保存結果と後処理

```text
batch-001/
  batch.json
  runs/
    doc-000001/manifest.json
    doc-000001/source/source.xdw
    doc-000001/pages/page-0001/...
    doc-000002/...
```

batch.jsonは形式docuworks-ocr-batch、schema_version 1.0の実行記録です。バッチID、入力・モデル・DLL設定、開始終了時刻、経過秒、文書の相対パス・短い文書ID・run相対パス・成否・エラーを保存します。成功時にはrun ID、原本SHA-256、総ページ数を記録します。失敗文書のこれらの値はnullです。構造はパッケージ内ocr-batch-1.0.schema.jsonに定義しています。

各文書は既存のOCR Result 1.1です。文書ごとにrun IDを割り当て、p0003-r000001等の領域IDはそのrun内で解釈します。全ページが正常推論で0領域でも成功です。ページごとの寸法と元ページ番号を保持します。batch.jsonは変更される実行記録で、内容を保証する署名ではありません。完成runのmanifest・ハッシュ検証は従来どおりです。

```powershell
python -m docuworks_integrations export-ocr --run-dir local-data/batch-001/runs/doc-000001 --format jsonl --output local-data/document-1.jsonl
python -m docuworks_integrations mark-region --run-dir local-data/batch-001/runs/doc-000001 --region-id p0003-r000001 --output-xdw local-data/marked.xdw --dry-run
```

実保存は--dry-runを外します。これらの後処理はOCRを実行しません。batch-dir全体を--run-dirに渡すことはできません。複数ページrunでは領域を文字列IDで指定します。

## 失敗・中断

GPUエンジンは1インスタンスを共有し、文書・ページを逐次処理します。文書ハンドルは文書ごとに閉じます。

文書の消失・アクセス拒否・原本変更、SDKのBAD_FORMAT、NEWFORMAT、FILE_NOT_FOUND、ACCESSDENIED、SHARING_VIOLATION、INVALID_ACCESS、PROTECT_MODULE、SIGNATURE_MODULEは文書固有エラーとして記録し次へ進みます。後者のSDKエラーは文書を開く／画像化する段階に限定します。失敗文書は完成runを公開せず、取得できた途中データはdiagnostics以下、原因はerror.jsonへ残します。文書を開く前の失敗はbatch.jsonだけに記録される場合があります。

推論・モデル・GPU・DLL利用不能、ディスク書込み障害、未知の内部例外、文書を閉じられない場合は全体を停止します。CPU切替や再試行はしません。完成済みrunを保持し、未着手はPENDINGで残します。batch.jsonは文書開始・終了ごとに一時ファイルから置換します。記録保存自体が失敗した場合は処理を止め、書き残されたRUNNINGを成功とは扱いません。Ctrl+CはINTERRUPTEDです。プロセス強制終了・電源断からの復旧／再開は今回対象外です。

文書状態はPENDING/RUNNING/SUCCEEDED/FAILED。バッチはRUNNING/COMPLETE/PARTIAL_FAILED/FAILED/INTERRUPTEDです。通常走査を終え一部だけ失敗した場合がPARTIAL_FAILED、全件失敗または共通障害で停止した場合がFAILEDです。

終了コードは全件成功0、失敗を含む終了1、引数不正2、中断130です。進捗とモデルログはstderr、実行が記録できた場合の最終batch JSONはstdoutへ出します。記録不能の場合はstderrで報告し1を返します。未処理・失敗を再実行するときは新しいバッチ出力先を指定します。

## Python API

```python
from docuworks_integrations import ocr_folder

result = ocr_folder("local-data/input", "local-data/batch-003", "models",
                    recursive=True, dpi=300, dll_path=None)
print(result.status, result.exit_code)
```

署名はocr_folder(input_dir, batch_dir, model_root, *, recursive=False, dpi=300, dll_path=None, engine=None) -> OcrBatchResultです。engineはOcrEngine互換の任意注入で、全文書で共有します。OcrBatchResult.documentsはBatchDocumentResultのリスト、to_dict()はJSON保存と同じ辞書、exit_codeはCLI終了コードです。事前条件違反は例外、実行中の通常障害は結果として返します。記録保存自体が継続して失敗した場合は例外です。外部から強制終了された記録を再開するAPIはありません。

APIのimport、保存結果の利用はPaddle/Pillow/OpenCV/DocuWorks DLLの読込みを必要としません。実OCRの呼出し時には既存環境が必要です。

## 検証

DLL不要テストで探索・保存順・複数文書の異寸法ページ・空ページ・モデル共有・文書失敗後の継続・共通障害の停止・中断・保存不能・後処理を検証します。実機試験とViewer確認は別記録にします。公開リポジトリへ文書・OCR結果・batch.json・モデル・DLLを追加しません。
