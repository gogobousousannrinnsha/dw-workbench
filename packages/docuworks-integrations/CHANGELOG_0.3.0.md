# 0.3.0 変更点

- OCRの生成・共通結果・保存結果の利用を分離。公開の結果型とload/save/get_region/export_jsonlを追加。
- manifest.json、版1.0、run UUID、ページ付き固定ID、px/mm座標、Raw、ハッシュを保存。
- CLIにconvert-ocr-runとexport-ocrを追加。mark-regionは新旧形式と原本パスの指定に対応。
- CLI ocr-xdwの出力形式を変更。既存OcrRegion・注釈APIとworkflow内の旧形式Python APIは維持。
- Core、採用済みGPU環境、モデルと0.2.0 wheelは保持。revision2のViewer記録だけユーザー報告を追記。
