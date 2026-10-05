# Integrations 0.2.0

- Core 1.0.0を変更せず、PaddleOcrEngine、AddMarker、build_marker_planを追加。
- OcrRegion.polygon（任意の4点）を追加。既存のJSON矩形入力は継続利用可能。
- ocr-xdw / mark-region CLI、BMP→PNG変換、番号付きプレビュー、OCR結果の保存を追加。
- 原本・プレビュー・認識結果のハッシュ検証と、書込み直前の再検証を追加。
- マーカーの再オープン検証は絶対Points座標、線幅・色・透過を確認。
- 既存annotate-imageの矩形→Textの順序を維持。
- 新機能の実行検証基準はPython 3.13 / Windows x64 / RTX 3060。
- PaddleOCR関連依存はocr extra。PaddlePaddle GPUは公式CUDA版を別途導入。
- 自動検証とViewer手動確認の状態を分離。
