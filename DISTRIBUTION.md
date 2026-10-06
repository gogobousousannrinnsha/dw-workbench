# Workbench 0.4.1 のダウンロード

[共通Portable v0.8.1](https://github.com/gogobousousannrinnsha/dw-ocr/releases/tag/v0.8.1)。

8個の `ocr_part_001_transport.zip` ～ `ocr_part_008_transport.zip` と `ocr_join_tools.zip` を取得し、同じ新しいフォルダーへ展開します。`join_parts.bat`で検査・結合し、できた`dw_ocr_with_code.zip`を別の新しいフォルダーへ展開して`Workbench開始.bat`を実行してください。旧版と元データを保持し、使用中のPortableへ上書きしないでください。移動前に保存してアプリとワーカーを通常終了します。

DocuWorks 10.1.1とRTX 3060の本PCで合成データを確認済みです。DocuWorks 9.1、別の物理PC、Viewer手操作、全DPI、CPU専用OCR、現地実帳票は未確認です。台帳注釈出力でWindows共有違反(WinError 32)が一度発生し、保存済みプレビューから再試行して成功しました。原本・確定データは保持されましたが、再現条件の特定と自動リトライ修正は未実施です。

[検証記録](docs/maintainer/RELEASE_v0.8.1.md)
