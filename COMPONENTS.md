# コンポーネントと固定ソース

| コンポーネント | 固定版 | ソース・責任 |
|---|---|---|
| DW-Workbench | 0.2.0 | [packages/dw-workbench](packages/dw-workbench)。業務モデル、SQLite保存、設定カタログ、案件処理、画面、出力 |
| docuworks-ctypes | 1.0.1 | [packages/docuworks-ctypes](packages/docuworks-ctypes)。XDWAPI接続、文書情報、読み取り・描画の基本API |
| docuworks-integrations | 0.13.0 | [packages/docuworks-integrations](packages/docuworks-integrations)。公開OCR接続等の固定コンパニオン。WorkbenchはPaddleOcrEngineを使用 |
| 説明書の入力・生成コード | v0.2.0 | [docs/manual-build](docs/manual-build)。図・合成サンプルを含む再生成資料 |

本公開リポジトリは新しいGit履歴を持つ独立スナップショットです。旧開発リポジトリの履歴は移植していません。[SOURCE_SNAPSHOT.json](SOURCE_SNAPSHOT.json)は3パッケージの実装Pythonファイルを相対パスとSHA-256で固定しています。wheelとPortableの実装はこのソースに対応します。

公開のために変更したのは、パッケージREADME・MITメタデータ、Workbenchテストの保存先、公開文書・CIです。Core／Integrations／Workbenchの実装 `.py` は固定元とバイト単位で一致します。テストは合成データを使用します。開発用の実帳票・案件・ログ・PC固有パスは配布対象にしません。

通常の実行依存はPython>=3.13、Tkinter、SQLite、Core>=1.0.1,<2、Integrations==0.13.0、Pillow>=11、XlsxWriter==3.2.9です。GPU OCRの依存と外部製品は[README](README.md)、第三者条件は[THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md)を参照してください。
