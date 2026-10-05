# Changes

## 0.4.0 — local candidate

- Keep 0.3.0 bulk template preview and transactional application.
- Navigate unfinished fields across project documents.
- Guide registration, templates, OCR, correction, Excel and ledger output.
- Match XLSX ledger rows without formula evaluation; preserve source mm anchors.
- Export reviewed rectangle annotations into new XDW copies.
- Use Integrations 0.14.0 source-bound OCR review reports.

# 変更履歴

## v0.3.0 候補

- 作業一覧に「複数文書へ一括適用」を追加。同じ案件の複数文書へ、登録テンプレートの同じ版をまとめて適用できます。
- ページ用テンプレートの対象を全ページ・範囲・奇数／偶数ページから選択できます。文書全体用にも対応します。
- 未割当だけへの適用を初期設定とし、適用・変更なし・スキップ・寸法不一致・処理単位変更をプレビューに表示します。
- 適用は複数文書を一つのトランザクションで保存します。古いプレビューの適用を拒否し、保存失敗時は全体を取り消します。
- 版切替では旧記録を履歴に残します。同じ版の再適用、OCR候補と採用値の責任、案件の保存形式、既存の案件単位出力は維持します。

新機能の操作は[一括適用の使い方](docs/bulk-template-application.md)を参照してください。v0.3.0候補はローカル検証用です。

## v0.2.0-restore.1

公開Portableの復元ヘルパーを修正し、診断と短い展開用フォルダーを追加しました。アプリはv0.2.0、Portable本体と説明書は従来版と同一です。
