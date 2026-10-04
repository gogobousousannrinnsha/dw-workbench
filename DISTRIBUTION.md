# 配布物の選び方

[v0.2.0の配布ページ](https://github.com/gogobousousannrinnsha/dw-workbench/releases/tag/v0.2.0)から取得します。この版は実帳票での受け入れ確認前の検証候補です。

| 目的 | 配布物 |
| --- | --- |
| アプリを使う | Portable ZIP。分割されている場合は全 `.zip.001` 以降の部品と復元用BAT・PS1・JSONを取得 |
| 使い方を読む | [図解操作マニュアルPDF](https://github.com/gogobousousannrinnsha/dw-workbench/releases/download/v0.2.0/DW-Workbench-v0.2.0-manual.pdf) |
| 説明書をオフラインで使う・練習する | [説明書ZIP](https://github.com/gogobousousannrinnsha/dw-workbench/releases/download/v0.2.0/DW-Workbench-v0.2.0-manual.zip)：PDF、HTML、合成XDW、Excel／CSVの完成例 |
| ソースを取得する | [ソースZIP](https://github.com/gogobousousannrinnsha/dw-workbench/releases/download/v0.2.0/DW-Workbench-v0.2.0-source.zip)、またはこのリポジトリのv0.2.0タグ |
| 同梱LGPL関連資産の対応ソースを取得する | 同じ配布ページの `third-party-sources-v0.1.0.zip` |
| ダウンロードを照合する | 同じ配布ページの `SHA256SUMS.txt` |

## Portableの準備

単一の `DW-Workbench-v0.2.0-Portable.zip` がある場合は展開してください。分割配布の場合は次の手順です。

1. 空の作業フォルダーへ、全ZIP部品、`Restore-Portable.bat`、`Restore-Portable.ps1`、`PORTABLE-MANIFEST.json` をダウンロードする。
2. `Restore-Portable.bat` を実行する。全部品と復元ZIPのSHA-256を照合し、同じ場所へ `DW-Workbench-v0.2.0` を展開する。復元ZIP・部品と展開先を合わせて約12GBの空きを用意する。
3. 展開フォルダーの `はじめに.md` を読む。`説明書/index.html` またはPDFの入門部分から始め、`起動.bat` を実行する。

復元用BATはWindows標準のPowerShellを使います。PCへのPython導入、管理者権限、PowerShell設定の恒久変更は不要です。部品不足や破損は表示して停止します。展開先のアプリフォルダーが既にある場合は停止するため、既存案件があるフォルダーへ上書きせず、別の場所で展開してください。

DocuWorks本体とNVIDIAドライバーはPortableに含まれません。原本表示にはDocuWorksが必要です。GPU OCRが使えなくても手入力・確認・保存・表出力の経路を利用できます。初期の `projects` と `settings` は空です。付属のサンプルは合成文書です。

保存し、アプリ・ワーカーを終了してからフォルダーを移動します。更新や移動の前に案件バックアップを作成してください。検証済みの範囲と未確認の条件は配布ページと同梱の検証案内を参照してください。
