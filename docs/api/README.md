# Python API案内

## 利用の流れ

```text
recognition.ocr_xdw_pages → 元OCR結果（Result 1.1）
  ├─ export_jsonl → 元結果のJSONL
  ├─ annotate_rectangles / render_text_maps → 矩形XDW・確認画像
  └─ create_review_xdw_regions → 編集用XDW + review.json
       → Viewer編集 → read_review_edits → 訂正候補
       → save_corrections → apply_corrections → export_effective_jsonl
```

| 目的 | 入口・参照先 |
|---|---|
| OCR環境を導入 | [セットアップ](setup.md) |
| 全ページ・指定ページを認識 | recognition.ocr_xdw_pages(input_xdw, run_dir, model_root, *, pages=None, dpi=300, dll_path=None, engine=None)。pages=Noneは全ページ、整数列は指定ページ。ocr_xdwはpage=1の単一ページ入口 |
| 元結果を読む・保存・JSONL出力 | [保存形式とAPIの正本](../../packages/docuworks-integrations/OCR_RESULT_FORMAT.md) |
| 文字だけを訂正 | [訂正API](corrections.md) |
| 1ページの指定領域を編集 | [複数領域レビューAPI](review-regions.md)。1件だけの指定も可能 |
| 形式1.0の互換レビュー | [単一領域API](review-single.md) |
| 全ページの白紙Review・独立した校正結果 | [Reviewed Result API](reviewed-result.md) |
| ID照合中心の取り込み・複数参照・付箋除外 | [Reviewed取り込み2.0](reviewed-import-v2.md) |
| テンプレートによる取得・独立した構造化結果 | [矩形テンプレート](../RECTANGLE_TEMPLATE.md) |
| 同じテンプレートの結果を文書ごとのCSVへ出力 | [Structured ResultのCSV出力](../STRUCTURED_CSV.md) |
| 矩形・確認画像・統合job | [派生出力と文書処理](processing.md) |
| DocuWorksの一般操作 | [Simple/Core/Rawの選択](core-layers.md)、[Core契約](core.md)、[Simpleの例](simple.md) |

保存結果の検証・訂正・JSONLはGPUとDLLを必要としません。XDWの生成・読取りにはCoreとDocuWorks DLL、確認画像にはPillow、OCRにはGPUとモデルを実行時に使用します。公開パッケージの依存宣言と、実行時importの要否は別です。

元OCR、訂正、訂正後結果は分離します。文字以外の領域ID・順序・座標・信頼度は保持します。未変更・選択対象外を「人が確認済み」と扱いません。訂正JSONは元runのIDとmanifestハッシュで照合し、一つでも不正なら全体を拒否します。自動合成や再OCRへの引継ぎはありません。

旧workflow.ocr_xdw / workflow.mark_regionは0.2.0形式の互換APIです。新規コードではrecognition/results/consumersを使用してください。旧関数名・引数・挙動は維持しています。
