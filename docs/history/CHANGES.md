> 履歴資料：整理前の記述を保存しています。現在の仕様・公開状況は[文書案内](../README.md)を参照してください。

# 0.7.0 正式統合 / Portable v0.3.0

- d31c2cbの訂正基盤・1領域/複数領域の原本重ね合わせ型XDWレビューを正式版へ昇格。公開APIと形式を維持。
- 公開ソースへSchema・日本語仕様・使用例を同梱。PortableではPython APIとして提供し、既存OCR入口を維持。
- 配布生成処理の版情報を照合し、公開v0.2.0のBAT修正と第三者資産を継承。
- ジョブと派生物の来歴に記録するIntegrations版を、固定値ではなく実行パッケージの版から取得するよう修正。
- 複数領域Viewerの正常1ケースは利用者報告と保存後コード照合で確認。異常操作・白紙型は未確認。
- 過去のdev版の検証記録は以下および各検証文書に保持する。

# 0.7.0.dev2 確認用XDW（開発版）

- 1ページ・1領域の原本重ね合わせ型XDW生成と編集候補の読取りを追加。
- 任意データ属性で識別し、既存修正基盤へ接続。Core・Portable・CLIは未変更。
- SDK自動往復とViewer未確認を分離。[仕様](../REVIEW_XDW_0.7.0.md)と[検証](../REVIEW_XDW_VERIFICATION.md)。

# 0.7.0.dev1 OCR文字訂正基盤（開発版）

- 元runを保持し、文字訂正セットを別JSONに保存・検証・適用するPython APIを追加。
- 元文字、座標、信頼度、修正セットの来歴を持つ利用用結果とJSONLを追加。
- Canonical 1.0/1.1と旧runに対応。Core・既存JSONL・CLI・Portableは維持。
- [仕様と使用例](../CORRECTIONS_0.7.0.md)、[検証記録](../CORRECTIONS_VERIFICATION.md)。

# 集約内容（2026-09-06）

- Core 1.0.0とIntegrations 0.3.0を `packages/` へ配置。Python/Schemaの全39ファイルは元wheelとバイト一致。
- READMEとdocsに導入、操作、Canonical OCR Result 1.0、旧結果移行、JSONL、OCR→Marker、検証記録、既知制約、ロードマップを整理。
- GPUの版固定lock、モデル期待hash、軽量結果利用の導入リストを `requirements/` へ集約。
- 引数式のPowerShellサンプル、モデル照合、公開対象監査と `.gitignore` を追加。
- Core配布監査ヘルパーの個人名入りパターンを一般的なユーザーパス検出へ変更。ライブラリ本体の変更ではありません。
- 元のJUnitからhostname/file属性を除去した公開用コピーと、今回のテスト集計を収録。実文書・認識済みデータ・生の実機ログは収録しない。
- Core 102件、Integrations 61件成功。ホスト固有/実機試験は除外。両wheelの再ビルド、空環境導入、pip check、合成bundle/JSONL/Marker dry-runとPowerShellサンプルを検証。
- PP-OCRv6モデルは既存ローカル資産のtar2件・展開ファイル6件を期待hashと照合。新規ダウンロード・GPU OCR・Viewerは再実施していない。
- 利用者の方針変更により、元のCODEXDOCWRRKSOCRへの変更ではなく、新規Privateリポジトリdocuworks-ocrへ集約。既存リポジトリの履歴・内容は変更しない。
