# Workbench 0.4.0 のダウンロード

[共通Portable v0.8.0](https://github.com/gogobousousannrinnsha/dw-ocr/releases/tag/v0.8.0) をダウンロードし、[READMEの起動手順](README.md#portableをダウンロードして使う)に従ってください。旧版の復元部品と混ぜず、新しいフォルダーへ展開します。

# v0.4.0公開Pre-release

今回の候補はDW-OCR v0.8.0との共通Portableで、`Workbench開始.bat`から起動します。初期のprojects・settingsは空です。全部品と結合ツールを同じ版でそろえ、新しいフォルダーへ展開してください。[別PCの条件と移動方法](docs/user/portable-transfer.md)を参照してください。

以下は既存公開版v0.2.0-restore.1の案内です。旧版の部品・manifestと新しい候補を混用しません。

# 配布物の選び方

[v0.2.0-restore.1の配布ページ](https://github.com/gogobousousannrinnsha/dw-workbench/releases/tag/v0.2.0-restore.1)から取得します。この版は実帳票での受け入れ確認前の検証候補です。復元用ヘルパーの保守版で、アプリはv0.2.0のままです。Portableの4つのZIP部品・説明書・アプリ実装は従来版と同一です。旧v0.2.0のタグと配布物を保持しています。

| 目的 | 配布物 |
| --- | --- |
| アプリを使う | Portable ZIP。分割されている場合は全 `.zip.001` 以降の部品と復元用BAT・PS1・JSONを取得 |
| 使い方を読む | [図解操作マニュアルPDF](https://github.com/gogobousousannrinnsha/dw-workbench/releases/download/v0.2.0-restore.1/DW-Workbench-v0.2.0-manual.pdf) |
| 説明書をオフラインで使う・練習する | [説明書ZIP](https://github.com/gogobousousannrinnsha/dw-workbench/releases/download/v0.2.0-restore.1/DW-Workbench-v0.2.0-manual.zip)：PDF、HTML、合成XDW、Excel／CSVの完成例 |
| ソースを取得する | [ソースZIP](https://github.com/gogobousousannrinnsha/dw-workbench/releases/download/v0.2.0-restore.1/DW-Workbench-v0.2.0-restore.1-source.zip)、またはこのリポジトリのv0.2.0-restore.1タグ |
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

## 復元でエラーが出た場合

v0.2.0-restore.1の `Restore-Portable.bat` と `Restore-Portable.ps1` を、ZIP部品と `PORTABLE-MANIFEST.json` があるフォルダーに置いて実行してください。旧版のヘルパーはこの2ファイルだけを置き換えます。確認済みの復元ZIPがある場合は再利用し、部品を再ダウンロードする必要はありません。サイズやSHA-256が一致しないZIPは再利用せず停止します。

短い展開先を試す場合は、先に空の `C:\DWRestore` フォルダーを作り、ダウンロード先で次のコマンドを実行します。ZIP部品・manifest・ヘルパーはダウンロード先に置いたままで構いません。

```powershell
.\Restore-Portable.bat "C:\DWRestore"
```

この例では `C:\DWRestore\DW-Workbench-v0.2.0` に展開します。展開先のアプリフォルダーが既にある場合は停止します。既存のPortableや案件へ上書きせず、別の空の展開先を選んでください。

修正版は余分な作業階層を減らして展開し、エラー時に処理段階・ZIP内ファイル名・対象パス・内部例外を表示します。ヘルパーのあるフォルダーに `Restore-Portable-error-日時-識別子.txt` を作成します。原因を確認するときは、このログと画面のエラーを参照してください。パスの長さ、空き容量、アクセス権等を切り分けるための情報であり、報告されたエラーの原因をパスの長さと断定したものではありません。ログを共有する際は、必要に応じてPCの利用者名や個別のパスを伏せてください。

失敗した途中の展開フォルダーは完成したアプリではありません。確認済みZIP、ZIP部品、既存フォルダーは残し、再試行時は新しい作業フォルダーを使います。途中のフォルダーから `起動.bat` を実行しないでください。
