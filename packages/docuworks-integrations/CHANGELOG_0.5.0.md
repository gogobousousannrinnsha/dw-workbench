# 0.5.0

- ocr-folderとocr_folder APIを追加。直下または--recursiveのXDWを順次処理し、文書ごとの全ページを独立runに保存します。
- OcrBatchResult、BatchDocumentResultとbatch JSON Schema 1.0を追加。進捗・失敗・未処理文書を保存します。
- 文書固有の既知エラーは継続し、GPU／モデル／DLL／記録保存／未知の障害は全体を停止します。エンジンはバッチで共有します。
- 完成runはOCR Result 1.1のまま、既存1.0読込み・旧API・マーカー・JSONL・Core 1.0.0を維持します。
- 公開配布監査でOCRバッチ実行記録の混入を拒否します。
- 並列処理・再開・自動再試行・バッチマーカーは対象外です。
