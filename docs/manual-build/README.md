# 説明書の再生成資料

DW-Workbench v0.2.0の公開用図解説明書を再生成する入稿データです。アプリを起動・操作・撮影する処理は含めません。
絶対PCパスは入稿から除き、UIソースの参照はリポジトリ内の packages/dw-workbench/dw_workbench/ui.py です。

## 生成

WindowsにPython 3.13以降と requirements.txt のライブラリを用意し、このフォルダーで実行します。

```powershell
python -m pip install -r requirements.txt
python -B -X utf8 build_manual.py
```

MeiryoのTTCフォントをWindowsのFontsから読みます。必要なら `--font` でTTF/TTCを指定できます。TTCのsubfontIndex=0を使います。
HTMLは `index.html`、PDFは `DW-Workbench_v0.2.0_図解操作マニュアル.pdf`、照合情報は `build-report.json` と `page-map.json` に出力します。
固定の入稿で128ページ・116操作・37掲載図を生成しました。フォントや生成ライブラリを変更した場合は、ページ配置を改めて確認してください。

`controls.json`・`dialogs.json`・`beginner_content.json` が本文、各manifest・figures.jsonが図の対応、assetsが画像、sample-input/sample-outputが合成見本です。
`make_diagrams.py` と `make_beginner_diagrams.py` はソースに基づくUI構成図を描く任意の再生成スクリプトです。撮影済み画像は再撮影しません。
入門PNGは合成fixtureをcanvasへ配置し、元画像を書き換えません。入力元PNGのハッシュを点検します。
図の出典を混ぜず、OCR精度・全GUI手動操作・実帳票受け入れを完了した証拠として扱わないでください。

## 読み取り照合

生成後に `python -B -X utf8 verify_public_manual.py` を実行すると、PDFページ数・PC絶対パスの残存・116操作のHTMLアンカー・相対リンク・合成Excel／CSVの型と値などを読み取りだけで照合します。
展開した説明書を照合する場合は `--manual` でそのフォルダーを指定してください。PDFの文字・図・表の配置は、別途全ページを画像に描画して点検します。

公開用資料のライセンスはリポジトリのLICENSEと第三者ライセンスを参照してください。
