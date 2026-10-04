# 配布補助と監査

- `verify_source.py` は固定実装のSHA-256と公開範囲を照合します。
- `verify_manual_inputs.py` は説明書の入力JSON・スクリプト・PNG・合成帳票／表見本を照合します。生成PDFの視覚確認は別に行います。
- `Restore-Portable.bat`／`Restore-Portable.ps1` はReleaseで配布するPortable分割ZIPをmanifestに従って結合・検証し、展開します。利用手順はReleaseの案内を参照してください。
- `package_assets.py` は配布担当者用です。`--root` で渡す作業フォルダーの `portable-staging/DW-Workbench-v0.2.0`、`manual-public`、`public-source` を入力にして、ZIP／分割資産を作成します。必要な作業配置とライセンス確認を済ませてから使用してください。通常のアプリ利用やソースビルドには不要です。

```powershell
python scripts/verify_source.py
python scripts/verify_manual_inputs.py
python scripts/package_assets.py --help
```
