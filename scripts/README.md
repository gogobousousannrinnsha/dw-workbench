# 配布補助と監査

- `verify_source.py` は固定実装のSHA-256と公開範囲を照合します。
- `verify_manual_inputs.py` は説明書の入力JSON・スクリプト・PNG・合成帳票／表見本を照合します。生成PDFの視覚確認は別に行います。
- `Restore-Portable.bat`／`Restore-Portable.ps1` はReleaseで配布するPortable分割ZIPをmanifestに従って結合・検証し、展開します。v0.2.0-restore.1では短い作業階層へ展開し、失敗した処理・ZIP内ファイル名・例外の詳細を診断ログに残します。利用手順は[配布物の案内](../DISTRIBUTION.md)を参照してください。
- `test_restore.py` はWindows PowerShellで復元用ヘルパーを検証します。小さな合成ZIPを使った17件で、ハッシュ照合、既存データの保護、不正なZIP内パスの拒否、別の展開先、途中失敗と再試行を確認します。実際の5GBのPortableや利用者の案件は使いません。試験用ファイルの親フォルダーは `DW_WORKBENCH_RESTORE_TEST_ROOT` で指定でき、CIではランナーの一時フォルダーを使います。
- `verify_bulk_template.py` はv0.3.0の複数文書への一括適用・保存失敗時の取消・案件出力を独立検証します。開発検証用の`openpyxl`が必要です。`--work-root`にソース外の作業フォルダーを指定してください。標準では合成100文書×10ページ×30項目の計測も行い、`--skip-load`で省略できます。実帳票・描画・OCR・画面操作の検証は含みません。
- `package_assets.py` は配布担当者用です。`--root` で渡す作業フォルダーの `portable-staging/DW-Workbench-v0.2.0`、`manual-public`、`public-source` を入力にして、ZIP／分割資産を作成します。必要な作業配置とライセンス確認を済ませてから使用してください。通常のアプリ利用やソースビルドには不要です。

```powershell
python scripts/verify_source.py
python scripts/verify_manual_inputs.py
python scripts/test_restore.py
python scripts/package_assets.py --help
```
