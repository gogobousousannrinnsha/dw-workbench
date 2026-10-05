# 白紙Reviewと独立した校正結果

Integrations 0.9.0の[ID照合中心の取り込み2.0](reviewed-import-v2.md)は明示的に選択します。以下の1.0のAPIは既定の厳格検証として維持します。

API・保存形式の正本は [Reviewed Result 1.0](../../packages/docuworks-integrations/REVIEWED_RESULT_FORMAT.md) です。
Portable v0.4.0ではOCR開始.batと校正結果取込.batから実行できます。[利用手順](../user/README.md)を参照してください。
Canonicalを原記録として保持し、Viewerで保存した現在の文字と位置を別の結果へ取り込みます。

[開発用実行手段](../../scripts/reviewed_dev.py) は `fixture`（合成テスト用）、`ocr`（実OCR）、`create`、`import`、`check` を提供します。
`ocr` には既存モデルのパスと専用 `--cache` を指定します。Portableやモデルの内容は更新しません。
各出力先は新規フォルダーにしてください。SDKの `--dll` はサブコマンドの前に指定します。

```text
python scripts/reviewed_dev.py --dll DLL_PATH fixture work/generated --pages 3
python scripts/reviewed_dev.py --dll DLL_PATH ocr work/generated/source.xdw work/real-run MODEL_PATH --cache work/cache
python scripts/reviewed_dev.py --dll DLL_PATH create work/real-run work/session
python scripts/reviewed_dev.py --dll DLL_PATH import work/session work/session/review.xdw work/result
python scripts/reviewed_dev.py check work/result
```

Viewer操作を挟む場合は `create` の後で編集・保存・閉じる操作を行います。
利用者にはPython実行を求めず、開発担当者が準備と取り込みを担当します。
