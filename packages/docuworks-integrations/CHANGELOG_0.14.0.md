# 0.14.0

- 元OCRの領域ID・原本SHA256・mm座標・文字・信頼度を保った確認一覧をJSONへ出力します。
- 低信頼度・空欄・信頼度不明などの確認理由と集計を出力します。領域の位置や採用値は変更しません。
- 公開APIの`build_review_report`／`export_review_report`とPortableの`OCR確認一覧.bat`を追加します。
- 既存のCanonical／Reviewed／テンプレートの保存形式と確認・訂正の正本を維持します。
