> 履歴資料：整理前の記述を保存しています。現在の仕様・公開状況は[文書案内](../README.md)を参照してください。

# OCRと保存結果の利用

リポジトリルートから実行し、実文書・出力はGit対象外の `local-data/` に置きます。runと出力ファイルには未使用名を指定してください。

フォルダ内のXDWを全ページOCRする場合は[フォルダバッチの操作・仕様](../BATCH_0.5.0.md)を参照してください。

## OCR → Canonical OCR Result 1.1

```powershell
New-Item -ItemType Directory -Force local-data | Out-Null
$dll = (Resolve-Path 'C:\Windows\System32\xdwapi.dll').Path
.\.venv-ocr\Scripts\python.exe -m docuworks_integrations ocr-xdw --input-xdw local-data/input.xdw --page 1 --dpi 300 --model-root models --run-dir local-data/run-001 --dll-path $dll
```

`--page` は元文書の1始まり番号、`--dpi` は300か600です。未指定は1ページ目、--all-pagesは全ページ、--pages 1,3-5は指定ページを処理します。詳細は[複数ページ仕様](../MULTIPAGE_0.4.0.md)を参照してください。完成runの `manifest.json` と `pages/page-0001/regions.md` / `preview.png` で結果とIDを確認します。原本コピーもrun内に入るため、run全体を公開しないでください。

## 旧0.2.0結果の移行

```powershell
.\.venv-results\Scripts\python.exe -m docuworks_integrations convert-ocr-run --run-dir local-data/old-run --output-dir local-data/converted-run
```

OCRもSDKも不要です。領域文字列・順序・座標・run_idを維持し、既存画像・Raw・プレビューを利用します。総ページ数やモデル情報が旧runにない場合は推測せずnull/unknownで残します。移行元を残し、新規出力を使います。

## JSONL

```powershell
.\.venv-results\Scripts\python.exe -m docuworks_integrations export-ocr --run-dir local-data/converted-run --format jsonl --output local-data/regions-001.jsonl
```

1領域1行で、run_id / manifest_sha256 / page / id、text、confidence、polygon_px / bbox_px / polygon_mm / bbox_mmを保存します。出力はbundle外に保存し、既存ファイルは上書きしません。

## Marker計画と保存

プレビューと領域一覧で対象IDを選びます。下記IDは例なので、実際の結果に置き換えてください。

```powershell
.\.venv-results\Scripts\python.exe -m docuworks_integrations mark-region --run-dir local-data/converted-run --region-id p0001-r000003 --input-xdw local-data/input.xdw --output-xdw local-data/marked-001.xdw --dry-run
.\.venv-results\Scripts\python.exe -m docuworks_integrations mark-region --run-dir local-data/converted-run --region-id p0001-r000003 --input-xdw local-data/input.xdw --output-xdw local-data/marked-001.xdw --dll-path $dll
```

`$dll` は上と同様に実際の製品DLLへ設定します。原本を移動した場合も `--input-xdw` で指定でき、保存済みSHA-256との一致が必須です。省略時は記録済みoriginal_pathを使うため、別PCでは明示指定を推奨します。

dry-runは計画JSONを標準出力に表示しXDWを作成しません。実保存は新規コピーに黄色・透過・水平2点のMarkerを付け、保存・再オープンして検証します。整数IDは処理ページが1つのrun限定なので、ページ込みのIDを推奨します。mark-region / export-ocrは旧runを直接読むこともできます。

自動検証後はViewerで重なり、文字の可読性、修復警告がないこと、選択と編集を確認します。実際に確認した版・ファイル・日付と項目を記録し、未確認項目は未確認と残します。

引数付きの実行サンプル: [OCR](../../examples/ocr.ps1)、[結果利用](../../examples/use-results.ps1)。Pythonで利用する場合は `recognition.ocr_xdw` / `consumers.mark_region` / `load_ocr_result` / `export_jsonl` が入口です。旧 `workflow` の互換関数は0.2.0形式用です。
