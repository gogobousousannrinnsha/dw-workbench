# DW-Workbench 0.4.1 Pre-release

未操作の採用欄へ最新の有効なOCRを自動入力しますが、状態は未確認です。原文と照合し「確認して次へ」またはCtrl+Enterで確認して進みます。手編集、意図的な空欄、確認済み、履歴不明の旧値は再OCRで上書きしません。寸法不一致は通常作業からスキップし、件数と一覧に残します。未割当は未完了のままです。保存形式2を維持します。

[操作の流れ](docs/WORKFLOW_UI_JA.md)、[一括適用](docs/BULK_TEMPLATE_JA.md)、[台帳・注釈](docs/LEDGER_MARKUP_JA.md)、[配布・検証記録](docs/maintainer/RELEASE_v0.8.1.md)を参照してください。

Core 1.0.1 / Integrations 0.14.0 / Python 3.13以降。採用値の正本は案件DBです。領域ID・原本ページ・mm座標を保持し、自作部分MITと第三者条件を維持します。

## Portableをダウンロードして使う

[共通Portable v0.8.1](https://github.com/gogobousousannrinnsha/dw-ocr/releases/tag/v0.8.1)。8個の `ocr_part_001_transport.zip` ～ `ocr_part_008_transport.zip` と `ocr_join_tools.zip` を取得し、同じ新しいフォルダーへ展開します。`join_parts.bat`で検査・結合し、できた`dw_ocr_with_code.zip`を別の新しいフォルダーへ展開して`Workbench開始.bat`を実行してください。旧版と元データを保持し、使用中のPortableへ上書きしないでください。移動前に保存してアプリとワーカーを通常終了します。

PythonとOCRモデルを同梱します。Windows x64、DocuWorks本体/XDWAPI、対応GPU/ドライバーが必要です。全コピーを保持する場合は空き16GB以上を目安にしてください。

DocuWorks 10.1.1とRTX 3060の本PCで合成データを確認済みです。DocuWorks 9.1、別の物理PC、Viewer手操作、全DPI、CPU専用OCR、現地実帳票は未確認です。台帳注釈出力でWindows共有違反(WinError 32)が一度発生し、保存済みプレビューから再試行して成功しました。原本・確定データは保持されましたが、再現条件の特定と自動リトライ修正は未実施です。
