# DW-Workbench v0.2.0

DocuWorks文書の項目を原本と照合し、採用値と根拠を保存して、案件ごとにExcel／CSVへ出力するWindowsデスクトップアプリです。文書全体用・1ページ用のテンプレートを登録し、ページごとに使うテンプレートを選べます。

**v0.2.0は検証候補のPre-releaseです。** DocuWorks 10.1での合成帳票・Portable移動等を検証しています。現地の実帳票とDocuWorks 9.1は未確認です。実帳票の認識精度や業務での最終受け入れを保証するものではありません。

## Portableを使う

[GitHub Release](https://github.com/gogobousousannrinnsha/dw-workbench/releases)からPortableと説明書を取得してください。大容量配布物の復元手順・ハッシュは該当Releaseの案内に従ってください。解凍後は `起動.bat` を使います。フォルダー移動は保存し、アプリとワーカーを終了してから行います。

取得するファイルとPortable復元の手順は[配布物の案内](DISTRIBUTION.md)にまとめています。

DocuWorks本体は外部依存です。GPU OCRには対応NVIDIA GPU・ドライバーと付属モデルが必要です。GPU OCRが使えない環境でも、DocuWorksの原本を表示して手入力・確認・保存・出力できます。

## ソースから実行する

Windows、Python 3.13以降、Tkinter、DocuWorksを用意してください。このリポジトリはPython、DocuWorks、ドライバー、OCRモデルを含みません。次の操作は通常の依存ライブラリを取得します。

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install ./packages/docuworks-ctypes ./packages/docuworks-integrations ./packages/dw-workbench
.\.venv\Scripts\python.exe -m dw_workbench --portable-root ./workbench-data
```

ソース実行では `--portable-root` を明示してください。設定・案件・作業ファイルは指定したフォルダーに作られます。Portable候補の既存案件を直接開く前に、アプリで案件バックアップを作成してください。

通常の手入力経路ではOCR依存の追加は不要です。ソースからGPU OCRを組み立てる場合は、固定版PaddleOCR 3.7.0／PaddleX 3.7.2、対応するPaddlePaddle GPUとNVIDIA環境、および `models/PP-OCRv6_medium_det` と `models/PP-OCRv6_medium_rec` のローカルモデルが必要です。モデルの実行時自動取得は行いません。GPU構成は[Release](https://github.com/gogobousousannrinnsha/dw-workbench/releases)の固定Portableを基準にしてください。

## ビルドと検証

```powershell
.\.venv\Scripts\python.exe -m pip wheel --no-build-isolation --no-deps --wheel-dir ./dist ./packages/docuworks-ctypes ./packages/docuworks-integrations ./packages/dw-workbench
.\.venv\Scripts\python.exe -m pip install pytest openpyxl
.\.venv\Scripts\python.exe scripts/verify_source.py
.\.venv\Scripts\python.exe -m pytest packages/dw-workbench/tests
```

GUIテストはWindowsデスクトップで実行してください。DocuWorks／GPUの実機試験と、合成データによる業務規則・保存・出力テストは別の検証です。GitHub ActionsはWindows上でソース監査・wheelビルド・Workbenchの合成テストを行います。

## ソースと説明書

- [コンポーネントと固定版の出所](COMPONENTS.md)
- [実装ファイルのハッシュ](SOURCE_SNAPSHOT.json)
- [図解説明書の再生成資料](docs/manual-build/README.md)
- [ライセンスの適用範囲](LICENSE_NOTICE.md)・[第三者コンポーネント](THIRD_PARTY_NOTICES.md)

公開用ソースは固定したv0.2.0から作成した独立スナップショットです。開発用Git履歴、実帳票、案件、ログは含みません。アプリの実装は変更せず、公開用パッケージメタデータとテストの出力先を整えています。
